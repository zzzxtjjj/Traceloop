"""Prepare the three small-appliance workspaces used by manual acceptance."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from core.db import init_db, session_scope
from core.models import ProjectMember, User
from core.schemas import ProjectCreate
from services.membership_service import add_project_member
from services.project_service import create_project, get_project_by_name

DEMOS = (
    ("demo1", "便携式空气炸锅 4L", ["US", "DE"]),
    ("demo2", "桌面空气净化器", ["US", "DE"]),
    ("demo3", "多功能电热水壶", ["US", "DE"]),
)


def main() -> None:
    init_db()
    with session_scope() as session:
        users = {user.email: user for user in session.scalars(select(User)).all()}
        bruce = users.get("xiongjunshu2007@qq.com")
        bruno = users.get("2484461477@qq.com")
        if not bruce or not bruno:
            raise RuntimeError("未找到布鲁斯或布鲁诺账号，请先完成账号初始化。")

        # Retire legacy demo identities without deleting rows referenced by history.
        for email in ("owner@tradeloop.demo", "quality@tradeloop.demo"):
            legacy = users.get(email)
            if legacy:
                legacy.active = False
                for membership in session.scalars(
                    select(ProjectMember).where(ProjectMember.user_id == legacy.id)
                ).all():
                    membership.status = "inactive"

        for name, product, markets in DEMOS:
            project = get_project_by_name(name)
            if project is None:
                project = create_project(
                    ProjectCreate(
                        name=name,
                        product_name=product,
                        access_code="demo2026",
                        markets=markets,
                    ),
                    owner_user_id=bruce.id,
                    session=session,
                )
            existing = session.scalar(
                select(ProjectMember).where(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == bruno.id,
                )
            )
            if existing is None:
                add_project_member(project.id, bruce.id, bruno.id, "quality", session=session)
            else:
                existing.role = "quality"
                existing.status = "active"
            for membership in session.scalars(
                select(ProjectMember).where(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == bruce.id,
                )
            ).all():
                membership.role = "owner"
                membership.status = "active"
        print("已准备 demo1、demo2、demo3；布鲁斯=负责人，布鲁诺=品控。")


if __name__ == "__main__":
    main()
