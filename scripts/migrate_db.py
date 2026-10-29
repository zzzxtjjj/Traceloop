import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{ROOT_DIR / 'data' / 'tradeloop.db'}"


def alembic_config(database_url: str | None = None) -> Config:
    load_dotenv(ROOT_DIR / ".env")
    url = database_url or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    config = Config(str(ROOT_DIR / "alembic.ini"))
    # ConfigParser treats percent signs as interpolation markers.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def upgrade_database(database_url: str | None = None) -> None:
    """Upgrade to the current schema without deleting the database or existing rows."""
    command.upgrade(alembic_config(database_url), "head")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upgrade a TradeLoop database without destructive resets."
    )
    parser.add_argument(
        "--database-url",
        help="Optional SQLAlchemy URL; defaults to DATABASE_URL or data/tradeloop.db.",
    )
    args = parser.parse_args(argv)
    try:
        upgrade_database(args.database_url)
    except Exception as exc:
        print(
            "数据库迁移失败。数据库未被自动删除。请先保留或恢复备份，"
            f"再检查迁移配置。错误类型：{type(exc).__name__}",
            file=sys.stderr,
        )
        return 1
    print("数据库已升级到当前版本；现有数据未被自动删除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
