"""Restore a previously created backup into a selected data directory."""

import argparse
import shutil
from pathlib import Path


def restore(source: Path, destination: Path) -> None:
    source = source.resolve()
    database_files = list(source.glob("*.db"))
    if len(database_files) != 1:
        raise ValueError("备份中必须且只能有一个 SQLite 数据库文件。")
    if (destination / database_files[0].name).exists() or (destination / "uploads").exists():
        raise FileExistsError("恢复目标已存在数据库或上传目录；请选择空的隔离目录。")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database_files[0], destination / database_files[0].name)
    uploads = source / "uploads"
    if uploads.exists():
        target = destination / "uploads"
        if target.exists():
            raise FileExistsError(f"目标上传目录已存在：{target}")
        shutil.copytree(uploads, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    restore(args.source, args.destination)
    print("恢复完成，请在启动前执行数据库健康检查。")
