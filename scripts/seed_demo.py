import os
import secrets
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.db import init_db  # noqa: E402
from core.schemas import ProjectCreate  # noqa: E402
from services.auth_service import set_password  # noqa: E402
from services.imports import import_quotes, list_quote_artifacts  # noqa: E402
from services.membership_service import (  # noqa: E402
    add_project_member,
    bootstrap_project_owner,
    create_user,
    get_user_by_email,
)
from services.project_service import create_project, get_project_by_name  # noqa: E402
from services.review_service import import_reviews, list_review_batches  # noqa: E402


def get_or_create_demo_user(display_name: str, email: str, password: str):
    user = get_user_by_email(email) or create_user(display_name, email)
    if not user.password_hash:
        set_password(user.id, password)
    return user


def main() -> None:
    init_db()
    demo_password = os.getenv("DEMO_PASSWORD", "").strip() or secrets.token_urlsafe(12)
    owner = get_or_create_demo_user(
        "演示项目负责人", "owner@tradeloop.demo", demo_password
    )
    procurement = get_or_create_demo_user(
        "演示采购", "procurement@tradeloop.demo", demo_password
    )
    operations = get_or_create_demo_user(
        "演示运营", "operations@tradeloop.demo", demo_password
    )
    quality = get_or_create_demo_user(
        "演示品控", "quality@tradeloop.demo", demo_password
    )
    project = get_project_by_name("保温杯新品出海")
    if project is None:
        project = create_project(
            ProjectCreate(
                name="保温杯新品出海",
                product_name="真空保温杯 750ml",
                access_code="demo2026",
                markets=["US", "DE"],
            ),
            owner_user_id=owner.id,
        )
    else:
        bootstrap_project_owner(project.id, owner.id)
    add_project_member(project.id, owner.id, procurement.id, "procurement")
    add_project_member(project.id, owner.id, operations.id, "operations")
    add_project_member(project.id, owner.id, quality.id, "quality")
    if not list_quote_artifacts(project.id):
        import_quotes(
            project.id,
            ROOT_DIR / "data" / "demo" / "supplier_quotes.csv",
            "首轮供应商报价",
        )
    if not list_review_batches(project.id):
        import_reviews(
            project_id=project.id,
            source=ROOT_DIR / "data" / "demo" / "reviews_before.csv",
            batch_name="包装改进前（模拟）",
        )
        import_reviews(
            project_id=project.id,
            source=ROOT_DIR / "data" / "demo" / "reviews_after.csv",
            batch_name="包装改进后（模拟）",
        )
    print(f"Demo project ready: id={project.id}, access_code=demo2026")
    print("Demo login password is supplied through DEMO_PASSWORD or generated for this run.")


if __name__ == "__main__":
    main()

