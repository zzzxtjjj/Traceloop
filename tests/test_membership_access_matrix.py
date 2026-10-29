import pytest
from sqlalchemy import func, select

from core.errors import ProjectAccessDeniedError
from core.models import ProjectMember
from core.schemas import ProjectCreate
from services.membership_service import (
    DENIED_MESSAGE,
    add_project_member,
    create_user,
    list_user_projects,
    require_project_member,
)
from services.project_service import create_project, verify_access_code


def _project(name: str, owner_user_id: int, db_session):
    return create_project(
        ProjectCreate(
            name=name,
            product_name=f"{name}产品",
            access_code="secure-2026",
            markets=["US", "DE"],
        ),
        owner_user_id=owner_user_id,
        session=db_session,
    )


def test_correct_access_code_does_not_grant_non_member_access(db_session) -> None:
    owner = create_user("Owner", "owner@example.test", session=db_session)
    outsider = create_user("Outsider", "outsider@example.test", session=db_session)
    project = _project("成员门禁", owner.id, db_session)

    assert verify_access_code("secure-2026", project.access_code_hash)
    with pytest.raises(ProjectAccessDeniedError, match=DENIED_MESSAGE):
        require_project_member(project.id, outsider.id, session=db_session)


def test_project_list_only_contains_active_member_projects(db_session) -> None:
    owner = create_user("Owner", "owner@example.test", session=db_session)
    other_owner = create_user("Other", "other@example.test", session=db_session)
    own_project = _project("可见项目", owner.id, db_session)
    _project("不可见项目", other_owner.id, db_session)

    visible = list_user_projects(owner.id, session=db_session)

    assert [project.id for project in visible] == [own_project.id]


def test_ordinary_member_cannot_add_project_member(db_session) -> None:
    owner = create_user("Owner", "owner@example.test", session=db_session)
    member = create_user("Member", "member@example.test", session=db_session)
    candidate = create_user("Candidate", "candidate@example.test", session=db_session)
    project = _project("角色权限", owner.id, db_session)
    add_project_member(
        project.id, owner.id, member.id, "quality", session=db_session
    )

    with pytest.raises(ProjectAccessDeniedError, match=DENIED_MESSAGE):
        add_project_member(
            project.id,
            member.id,
            candidate.id,
            "operations",
            session=db_session,
        )

    assert db_session.scalar(
        select(func.count(ProjectMember.id)).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == candidate.id,
        )
    ) == 0


def test_owner_can_add_project_member(db_session) -> None:
    owner = create_user("Owner", "owner@example.test", session=db_session)
    candidate = create_user("Candidate", "candidate@example.test", session=db_session)
    project = _project("负责人操作", owner.id, db_session)

    membership = add_project_member(
        project.id,
        owner.id,
        candidate.id,
        "procurement",
        session=db_session,
    )

    assert membership.project_id == project.id
    assert membership.user_id == candidate.id
    assert membership.role == "procurement"
    assert membership.status == "active"


def test_same_user_cannot_have_duplicate_membership_in_project(db_session) -> None:
    owner = create_user("Owner", "owner@example.test", session=db_session)
    candidate = create_user("Candidate", "candidate@example.test", session=db_session)
    project = _project("成员唯一性", owner.id, db_session)

    first = add_project_member(
        project.id, owner.id, candidate.id, "quality", session=db_session
    )
    second = add_project_member(
        project.id, owner.id, candidate.id, "quality", session=db_session
    )

    assert second.id == first.id
    assert db_session.scalar(
        select(func.count(ProjectMember.id)).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == candidate.id,
        )
    ) == 1


def test_inactive_user_and_inactive_membership_are_denied(db_session) -> None:
    owner = create_user("Owner", "owner@example.test", session=db_session)
    inactive_user = create_user(
        "Inactive User", "inactive-user@example.test", session=db_session
    )
    inactive_member = create_user(
        "Inactive Member", "inactive-member@example.test", session=db_session
    )
    project = _project("停用门禁", owner.id, db_session)
    user_membership = add_project_member(
        project.id, owner.id, inactive_user.id, "quality", session=db_session
    )
    member_membership = add_project_member(
        project.id, owner.id, inactive_member.id, "operations", session=db_session
    )

    inactive_user.active = False
    member_membership.status = "inactive"
    db_session.flush()

    with pytest.raises(ProjectAccessDeniedError, match=DENIED_MESSAGE):
        require_project_member(project.id, inactive_user.id, session=db_session)
    with pytest.raises(ProjectAccessDeniedError, match=DENIED_MESSAGE):
        require_project_member(project.id, inactive_member.id, session=db_session)
    assert list_user_projects(inactive_user.id, session=db_session) == []
    assert user_membership.status == "active"


def test_access_denial_does_not_disclose_project_or_user_information(
    db_session,
) -> None:
    owner = create_user("Secret Owner", "secret-owner@example.test", session=db_session)
    outsider = create_user(
        "Secret Outsider", "secret-outsider@example.test", session=db_session
    )
    project = _project("绝密项目名称", owner.id, db_session)

    with pytest.raises(ProjectAccessDeniedError) as captured:
        require_project_member(project.id, outsider.id, session=db_session)

    message = str(captured.value)
    assert message == DENIED_MESSAGE
    assert str(project.id) not in message
    assert str(outsider.id) not in message
    assert project.name not in message
    assert outsider.display_name not in message
    assert outsider.email not in message
