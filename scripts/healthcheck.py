"""Read-only local health check used by systemd/operations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import database_health, engine
from core.models import Base


def main() -> int:
    health = database_health()
    tables = set(Base.metadata.tables)
    existing = set(__import__("sqlalchemy").inspect(engine).get_table_names())
    missing = tables - existing
    if missing:
        print(f"数据库缺少表：{', '.join(sorted(missing))}")
        return 1
    print(f"ok journal_mode={health['journal_mode']} busy_timeout_ms={health['busy_timeout_ms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
