import json
import sqlite3
import subprocess
from pathlib import Path

from core.config import Settings
from services.release_verification import report_as_json, verify_release


class FakeRunner:
    def __init__(
        self,
        *,
        dirty: bool = False,
        failures: set[str] | None = None,
        upstream: str = "same",
    ) -> None:
        self.dirty = dirty
        self.failures = failures or set()
        self.upstream = upstream
        self.commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        command_text = " ".join(command)
        if "rev-parse" in command_text and "@{upstream}" in command:
            if self.upstream == "none":
                return subprocess.CompletedProcess(command, 128, stdout="", stderr="")
            upstream_hash = "abc123" if self.upstream == "same" else "def456"
            return subprocess.CompletedProcess(
                command, 0, stdout=f"{upstream_hash}\n", stderr=""
            )
        if "rev-parse" in command_text:
            return subprocess.CompletedProcess(command, 0, stdout="abc123\n", stderr="")
        if "rev-list" in command_text:
            return subprocess.CompletedProcess(command, 0, stdout="2\t3\n", stderr="")
        if "git status" in command_text:
            stdout = " M private-name.txt\n" if self.dirty else ""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        tool = "pytest" if "pytest" in command else "ruff"
        code = 1 if tool in self.failures else 0
        return subprocess.CompletedProcess(
            command,
            code,
            stdout="customer text that must not appear",
            stderr="secret diagnostic that must not appear",
        )


def make_release_tree(root: Path, *, with_database: bool = True) -> str:
    for relative in (
        "app.py",
        "README.md",
        "requirements.txt",
        ".env.example",
        "alembic.ini",
        "scripts/migrate_db.py",
        "scripts/seed_demo.py",
        "migrations/versions/0002_project_membership.py",
        "deliverables/poster/tradeloop_poster.svg",
        "deliverables/pitch/index.html",
        "deliverables/pitch/THREE_MINUTE_SCRIPT.md",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")
    (root / "migrations/versions/0002_project_membership.py").write_text(
        'revision = "0002_project_membership"\n', encoding="utf-8"
    )
    (root / "deliverables/poster/tradeloop_poster.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="800mm" height="1800mm"/>',
        encoding="utf-8",
    )
    pages = root / "pages"
    pages.mkdir()
    for number in range(1, 8):
        (pages / f"0{number}_page.py").write_text("", encoding="utf-8")

    database = root / "data" / "tradeloop.db"
    if with_database:
        database.parent.mkdir()
        connection = sqlite3.connect(database)
        connection.executescript(
            """
            CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);
            CREATE TABLE project_members (
                id INTEGER PRIMARY KEY, project_id INTEGER, user_id INTEGER,
                role TEXT, status TEXT
            );
            CREATE TABLE alembic_version (version_num TEXT NOT NULL);
            INSERT INTO alembic_version VALUES ('0002_project_membership');
            INSERT INTO projects VALUES (1, '保温杯新品出海');
            """
        )
        for user_id, email in enumerate(
            (
                "owner@tradeloop.demo",
                "procurement@tradeloop.demo",
                "operations@tradeloop.demo",
                "quality@tradeloop.demo",
            ),
            start=1,
        ):
            connection.execute("INSERT INTO users VALUES (?, ?)", (user_id, email))
            connection.execute(
                "INSERT INTO project_members VALUES (?, 1, ?, ?, 'active')",
                (user_id, user_id, "owner" if user_id == 1 else "member"),
            )
        connection.commit()
        connection.close()
    return f"sqlite:///{database.as_posix()}"


def safe_config(database_url: str, *, api_key: str = "never-print-this-key") -> Settings:
    return Settings(
        database_url=database_url,
        model_api_key=api_key,
        model_name="offline-model",
        model_base_url="https://models.example.test/v1",
        model_timeout_seconds=10,
        model_max_input_chars=1000,
        model_max_reviews_per_run=10,
        model_max_attempts=1,
    )


def test_quick_verification_passes_complete_offline_release(tmp_path) -> None:
    database_url = make_release_tree(tmp_path)
    runner = FakeRunner()

    report = verify_release(
        root_dir=tmp_path,
        database_url=database_url,
        config=safe_config(database_url),
        runner=runner,
    )

    assert report.exit_code == 0
    assert report.counts == {"pass": 10, "warning": 0, "fail": 0}
    assert len(runner.commands) == 3
    assert all("--live" not in command for command in runner.commands)
    serialized = report_as_json(report)
    assert "never-print-this-key" not in serialized
    assert "customer" not in serialized


def test_missing_database_is_warning_and_does_not_fail(tmp_path) -> None:
    database_url = make_release_tree(tmp_path, with_database=False)

    report = verify_release(
        root_dir=tmp_path,
        database_url=database_url,
        config=safe_config(database_url),
        runner=FakeRunner(),
    )

    demo_check = next(item for item in report.checks if item.name == "demo_data")
    assert demo_check.status == "warning"
    assert report.exit_code == 0


def test_database_revision_must_really_be_at_0002(tmp_path) -> None:
    database_url = make_release_tree(tmp_path)
    connection = sqlite3.connect(tmp_path / "data/tradeloop.db")
    connection.execute("UPDATE alembic_version SET version_num = '0001_current_schema'")
    connection.commit()
    connection.close()

    report = verify_release(
        root_dir=tmp_path,
        database_url=database_url,
        config=safe_config(database_url),
        runner=FakeRunner(),
    )

    check = next(item for item in report.checks if item.name == "demo_data")
    assert check.status == "fail"
    assert "0002" in check.summary


def test_poster_qr_placeholder_is_warning_only(tmp_path) -> None:
    database_url = make_release_tree(tmp_path)
    poster = tmp_path / "deliverables/poster/tradeloop_poster.svg"
    poster.write_text(
        '<svg width="800mm" height="1800mm"><text>二维码占位</text></svg>',
        encoding="utf-8",
    )

    report = verify_release(
        root_dir=tmp_path,
        database_url=database_url,
        config=safe_config(database_url),
        runner=FakeRunner(),
    )

    check = next(item for item in report.checks if item.name == "poster")
    assert check.status == "warning"
    assert report.exit_code == 0


def test_incomplete_seed_and_dirty_worktree_are_failures_without_leaking_paths(
    tmp_path,
) -> None:
    database_url = make_release_tree(tmp_path)
    connection = sqlite3.connect(tmp_path / "data/tradeloop.db")
    connection.execute("DELETE FROM project_members WHERE id = 4")
    connection.commit()
    connection.close()

    report = verify_release(
        root_dir=tmp_path,
        database_url=database_url,
        config=safe_config(database_url),
        runner=FakeRunner(dirty=True),
    )

    assert report.exit_code == 1
    assert next(item for item in report.checks if item.name == "demo_data").status == "fail"
    git_check = next(item for item in report.checks if item.name == "git_worktree")
    assert git_check.status == "fail"
    assert "private-name" not in git_check.summary


def test_missing_upstream_is_warning_without_network_access(tmp_path) -> None:
    database_url = make_release_tree(tmp_path)
    runner = FakeRunner(upstream="none")

    report = verify_release(
        root_dir=tmp_path,
        database_url=database_url,
        config=safe_config(database_url),
        runner=runner,
    )

    check = next(item for item in report.checks if item.name == "git_upstream")
    assert check.status == "warning"
    assert report.exit_code == 0
    assert all("fetch" not in command for command in runner.commands)


def test_diverged_upstream_is_failure_with_counts_only(tmp_path) -> None:
    database_url = make_release_tree(tmp_path)
    runner = FakeRunner(upstream="different")

    report = verify_release(
        root_dir=tmp_path,
        database_url=database_url,
        config=safe_config(database_url),
        runner=runner,
    )

    check = next(item for item in report.checks if item.name == "git_upstream")
    assert check.status == "fail"
    assert "ahead=2" in check.summary
    assert "behind=3" in check.summary
    assert "abc123" not in check.summary
    assert "def456" not in check.summary
    assert report.exit_code == 1
    assert all("fetch" not in command for command in runner.commands)


def test_full_mode_runs_pytest_then_ruff_and_sanitizes_output(tmp_path) -> None:
    database_url = make_release_tree(tmp_path)
    runner = FakeRunner(failures={"ruff"})

    report = verify_release(
        root_dir=tmp_path,
        database_url=database_url,
        config=safe_config(database_url),
        full=True,
        runner=runner,
    )

    tools = [command for command in runner.commands if "-m" in command]
    assert "pytest" in tools[0]
    assert "ruff" in tools[1]
    assert all("--live" not in command for command in runner.commands)
    assert next(item for item in report.checks if item.name == "pytest").status == "pass"
    assert next(item for item in report.checks if item.name == "ruff").status == "fail"
    output = report_as_json(report)
    assert "customer text" not in output
    assert "secret diagnostic" not in output
    assert report.exit_code == 1


def test_json_report_has_stable_public_shape(tmp_path) -> None:
    database_url = make_release_tree(tmp_path, with_database=False)
    report = verify_release(
        root_dir=tmp_path,
        database_url=database_url,
        config=safe_config(database_url, api_key=""),
        runner=FakeRunner(),
    )

    payload = json.loads(report_as_json(report))
    assert set(payload) == {"exit_code", "counts", "checks"}
    assert payload["exit_code"] == 0
    assert payload["counts"]["warning"] == 2
    assert all(set(item) == {"name", "status", "summary"} for item in payload["checks"])
