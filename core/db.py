from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings
from core.models import Base

settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


def init_db() -> None:
    """Create missing tables. This is intentionally lightweight for the hackathon V1."""
    Base.metadata.create_all(bind=engine)


def database_health() -> dict[str, str]:
    """Run a lightweight read-only database health check."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar()
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar()
    return {"status": "ok", "journal_mode": str(journal_mode), "busy_timeout_ms": str(busy_timeout)}


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_context(session: Session | None = None) -> Generator[Session, None, None]:
    """Use a caller-owned session in tests/composed services, or create a transaction."""
    if session is not None:
        yield session
        return
    with session_scope() as managed:
        yield managed

