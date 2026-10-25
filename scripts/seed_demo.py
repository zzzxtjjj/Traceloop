import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.db import init_db  # noqa: E402
from core.schemas import ProjectCreate  # noqa: E402
from services.imports import import_quotes, list_quote_artifacts  # noqa: E402
from services.project_service import create_project, get_project_by_name  # noqa: E402


def main() -> None:
    init_db()
    project = get_project_by_name("保温杯新品出海")
    if project is None:
        project = create_project(
            ProjectCreate(
                name="保温杯新品出海",
                product_name="真空保温杯 750ml",
                access_code="demo2026",
                markets=["US", "DE"],
            )
        )
    if not list_quote_artifacts(project.id):
        import_quotes(
            project.id,
            ROOT_DIR / "data" / "demo" / "supplier_quotes.csv",
            "首轮供应商报价",
        )
    print(f"Demo project ready: id={project.id}, access_code=demo2026")


if __name__ == "__main__":
    main()

