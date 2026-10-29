from sqlalchemy import create_engine, inspect, select, text

from core.models import Artifact, Base, Project, SupplierQuote
from scripts import migrate_db


def sqlite_url(path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_empty_database_upgrades_to_current_schema(tmp_path) -> None:
    database_path = tmp_path / "empty.db"
    url = sqlite_url(database_path)

    migrate_db.upgrade_database(url)

    engine = create_engine(url)
    table_names = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables).issubset(table_names)
    assert "alembic_version" in table_names
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0001_current_schema"
        )


def test_first_stage_database_upgrade_preserves_projects_artifacts_and_quotes(
    tmp_path,
) -> None:
    database_path = tmp_path / "legacy.db"
    url = sqlite_url(database_path)
    engine = create_engine(url)
    Project.__table__.create(engine)
    Artifact.__table__.create(engine)
    SupplierQuote.__table__.create(engine)
    with engine.begin() as connection:
        project_id = connection.execute(
            Project.__table__.insert().values(
                name="Legacy project",
                product_name="Bottle",
                access_code_hash="legacy-hash",
                markets_json='["US"]',
            )
        ).inserted_primary_key[0]
        artifact_id = connection.execute(
            Artifact.__table__.insert().values(
                project_id=project_id,
                artifact_type="quote_csv",
                batch_name="Legacy quotes",
                original_filename="legacy.csv",
                stored_path="legacy.csv",
                sha256="a" * 64,
                parse_status="valid",
            )
        ).inserted_primary_key[0]
        connection.execute(
            SupplierQuote.__table__.insert().values(
                artifact_id=artifact_id,
                supplier="Legacy supplier",
                unit_price=9.5,
                currency="USD",
                moq=100,
                lead_time_days=20,
                payment_terms="30% deposit",
                quality_note="Legacy row must remain",
            )
        )

    migrate_db.upgrade_database(url)

    with engine.connect() as connection:
        assert connection.scalar(select(Project.name)) == "Legacy project"
        assert connection.scalar(select(Artifact.original_filename)) == "legacy.csv"
        assert connection.scalar(select(SupplierQuote.supplier)) == "Legacy supplier"
        assert connection.scalar(select(SupplierQuote.quality_note)) == (
            "Legacy row must remain"
        )
    assert set(Base.metadata.tables).issubset(set(inspect(engine).get_table_names()))


def test_repeated_upgrade_is_idempotent(tmp_path) -> None:
    url = sqlite_url(tmp_path / "repeat.db")

    migrate_db.upgrade_database(url)
    migrate_db.upgrade_database(url)

    engine = create_engine(url)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM alembic_version")) == 1
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0001_current_schema"
        )


def test_cli_failure_warns_about_backup_and_never_deletes_database(
    tmp_path, monkeypatch, capsys
) -> None:
    database_path = tmp_path / "keep.db"
    url = sqlite_url(database_path)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sentinel (value TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO sentinel (value) VALUES ('keep me')"))

    def fail_upgrade(_database_url=None):
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(migrate_db, "upgrade_database", fail_upgrade)
    assert migrate_db.main(["--database-url", url]) == 1

    error = capsys.readouterr().err
    assert "迁移失败" in error
    assert "未被自动删除" in error
    assert "备份" in error
    assert database_path.exists()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT value FROM sentinel")) == "keep me"
