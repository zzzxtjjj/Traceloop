import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text

from core.errors import ProjectAccessDeniedError
from core.models import Project, ProjectMember, User
from core.schemas import ProjectCreate
from scripts.migrate_db import upgrade_database
from services.membership_service import (
    UserEmailExistsError,
    add_project_member,
    bootstrap_project_owner,
    create_user,
    list_project_members,
    list_user_projects,
    list_users,
    require_project_member,
    require_project_role,
)
from services.project_service import create_project, verify_access_code

ROOT_DIR = Path(__file__).resolve().parents[1]


def project_payload(name: str) -> ProjectCreate:
    return ProjectCreate(
        name=name,
        product_name="Bottle",
        access_code="demo2026",
        markets=["US"],
    )


def test_create_user_normalizes_unique_email_and_keeps_session_usable(db_session) -> None:
    first = create_user("Owner", " Owner@Example.COM ", session=db_session)
    assert first.email == "owner@example.com"
    with pytest.raises(UserEmailExistsError):
        create_user("Duplicate", "owner@example.com", session=db_session)

    second = create_user("Quality", "quality@example.com", session=db_session)
    assert second.id is not None
    assert [item.id for item in list_users(session=db_session)] == [first.id, second.id]


def test_project_creation_can_atomically_create_owner_membership(db_session) -> None:
    owner = create_user("Owner", "owner@example.com", session=db_session)

    project = create_project(
        project_payload("Owned project"),
        owner_user_id=owner.id,
        session=db_session,
    )

    membership = require_project_role(project.id, owner.id, {"owner"}, session=db_session)
    assert membership.status == "active"
    assert [item.id for item in list_user_projects(owner.id, session=db_session)] == [
        project.id
    ]


def test_legacy_project_creation_remains_compatible_and_access_code_grants_no_member(
    db_session,
) -> None:
    user = create_user("Visitor", "visitor@example.com", session=db_session)

    project = create_project(project_payload("Legacy-compatible"), session=db_session)

    assert verify_access_code("demo2026", project.access_code_hash)
    assert not list(
        db_session.scalars(
            select(ProjectMember).where(ProjectMember.project_id == project.id)
        )
    )
    with pytest.raises(ProjectAccessDeniedError, match="无权"):
        require_project_member(project.id, user.id, session=db_session)


def test_owner_adds_member_idempotently_and_member_cannot_add_others(db_session) -> None:
    owner = create_user("Owner", "owner@example.com", session=db_session)
    quality = create_user("Quality", "quality@example.com", session=db_session)
    other = create_user("Other", "other@example.com", session=db_session)
    project = create_project(
        project_payload("Member project"), owner_user_id=owner.id, session=db_session
    )

    first = add_project_member(
        project.id, owner.id, quality.id, "quality", session=db_session
    )
    second = add_project_member(
        project.id, owner.id, quality.id, "quality", session=db_session
    )

    assert first.id == second.id
    assert db_session.scalar(
        select(text("count(*)")).select_from(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == quality.id,
        )
    ) == 1
    with pytest.raises(ProjectAccessDeniedError, match="无权"):
        add_project_member(
            project.id, quality.id, other.id, "operations", session=db_session
        )
    members = list_project_members(project.id, owner.id, session=db_session)
    assert {(item.user_id, item.role) for item in members} == {
        (owner.id, "owner"),
        (quality.id, "quality"),
    }


def test_inactive_user_or_membership_is_denied_without_object_details(db_session) -> None:
    owner = create_user("Owner", "owner@example.com", session=db_session)
    member = create_user("Member", "member@example.com", session=db_session)
    project = create_project(
        project_payload("Inactive project"), owner_user_id=owner.id, session=db_session
    )
    membership = add_project_member(
        project.id, owner.id, member.id, "operations", session=db_session
    )

    member.active = False
    with pytest.raises(ProjectAccessDeniedError) as inactive_user:
        require_project_member(project.id, member.id, session=db_session)
    assert str(inactive_user.value) == "当前用户无权执行该项目操作。"

    member.active = True
    membership.status = "inactive"
    with pytest.raises(ProjectAccessDeniedError) as inactive_member:
        require_project_member(project.id, member.id, session=db_session)
    assert str(inactive_member.value) == "当前用户无权执行该项目操作。"


def test_legacy_project_can_bootstrap_only_one_owner(db_session) -> None:
    first = create_user("First owner", "first@example.com", session=db_session)
    second = create_user("Second owner", "second@example.com", session=db_session)
    project = create_project(project_payload("Legacy owner"), session=db_session)

    owner = bootstrap_project_owner(project.id, first.id, session=db_session)
    assert bootstrap_project_owner(project.id, first.id, session=db_session).id == owner.id
    with pytest.raises(ProjectAccessDeniedError):
        bootstrap_project_owner(project.id, second.id, session=db_session)


def test_membership_migration_supports_fresh_and_already_stamped_0001_databases(
    tmp_path,
) -> None:
    fresh_url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    upgrade_database(fresh_url)
    fresh_engine = create_engine(fresh_url)
    assert {"users", "project_members"}.issubset(
        set(inspect(fresh_engine).get_table_names())
    )
    with fresh_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0002_project_membership"
        )

    legacy_url = f"sqlite:///{(tmp_path / 'stamped-0001.db').as_posix()}"
    legacy_engine = create_engine(legacy_url)
    Project.__table__.create(legacy_engine)
    with legacy_engine.begin() as connection:
        connection.execute(
            Project.__table__.insert().values(
                name="Preserved legacy project",
                product_name="Bottle",
                access_code_hash="legacy",
                markets_json='["US"]',
            )
        )
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('0001_current_schema')")
        )

    upgrade_database(legacy_url)

    assert {"users", "project_members"}.issubset(
        set(inspect(legacy_engine).get_table_names())
    )
    with legacy_engine.connect() as connection:
        assert connection.scalar(select(Project.name)) == "Preserved legacy project"
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0002_project_membership"
        )


def test_seed_demo_creates_members_idempotently(tmp_path) -> None:
    database_path = tmp_path / "seed-demo.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "scripts/seed_demo.py"],
            cwd=ROOT_DIR,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr

    engine = create_engine(environment["DATABASE_URL"])
    with engine.connect() as connection:
        assert connection.scalar(select(text("count(*)")).select_from(User)) == 4
        assert connection.scalar(select(text("count(*)")).select_from(ProjectMember)) == 4
