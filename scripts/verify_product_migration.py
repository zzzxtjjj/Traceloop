"""Exercise upgrade/downgrade on a snapshot, preserving every legacy row."""

import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy.engine import make_url

from core.config import settings
from scripts.migrate_db import alembic_config

MIGRATION_ADDED_COLUMNS = {
    "tasks": {"description", "assignee_user_id", "priority"},
    "reviews": {"review_date"},
}


def fingerprint(connection, tables):
    result = {}
    for table in tables:
        all_columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        columns = [
            column
            for column in all_columns
            if column not in MIGRATION_ADDED_COLUMNS.get(table, set())
        ]
        projection = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
        rows = connection.execute(f'SELECT {projection} FROM "{table}"').fetchall()
        result[table] = hashlib.sha256(
            json.dumps(sorted(rows, key=repr), default=str, ensure_ascii=True).encode()
        ).hexdigest()
    return result


def main():
    source = Path(make_url(settings.database_url).database)
    with tempfile.TemporaryDirectory(prefix="tradeloop-migration-") as directory:
        copy = Path(directory) / "isolated.db"
        with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(copy)) as dst:
                src.backup(dst)
        with closing(sqlite3.connect(copy)) as db:
            tables = [
                r[0]
                for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                if r[0] not in {"alembic_version", "product_entity_links", "auth_throttles"}
            ]
            before = fingerprint(db, tables)
        config = alembic_config(f"sqlite:///{copy.as_posix()}")
        command.upgrade(config, "head")
        command.downgrade(config, "0007_project_archive")
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with closing(sqlite3.connect(copy)) as db:
            unchanged = before == fingerprint(db, tables)
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            version = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            task_indexes = {
                row[1] for row in db.execute("PRAGMA index_list(tasks)").fetchall()
            }
            task_foreign_keys = {
                row[3] for row in db.execute("PRAGMA foreign_key_list(tasks)").fetchall()
            }
            assignee_integrity = (
                "ix_tasks_assignee_user_id" in task_indexes
                and "assignee_user_id" in task_foreign_keys
            )
        result = {
            "isolated": True,
            "legacy_tables_unchanged": unchanged,
            "legacy_table_count": len(tables),
            "integrity_check": integrity,
            "version": version,
            "task_assignee_fk_index": "PASS" if assignee_integrity else "FAIL",
            "upgrade_downgrade_upgrade": "PASS" if unchanged else "FAIL",
        }
        print(json.dumps(result))
        return 0 if unchanged and integrity == "ok" and assignee_integrity else 1


if __name__ == "__main__":
    raise SystemExit(main())
