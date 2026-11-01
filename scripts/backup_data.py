"""Create a consistent SQLite and upload-directory backup."""

import argparse
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from core.config import settings


def backup(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = destination / stamp
    target.mkdir()
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    with sqlite3.connect(database_path) as source, sqlite3.connect(
        target / database_path.name
    ) as copy:
        source.backup(copy)
    if settings.upload_dir.exists():
        shutil.copytree(settings.upload_dir, target / "uploads")
    (target / "MANIFEST.txt").write_text(
        f"database={database_path.name}\nupload_dir={settings.upload_dir}\n",
        encoding="utf-8",
    )
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=settings.data_dir / "backups")
    args = parser.parse_args()
    print(backup(args.destination))
