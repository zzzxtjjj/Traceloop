import pytest
from sqlalchemy import select

from core.errors import ProjectAccessDeniedError
from core.models import AuthSession
from core.schemas import ProjectCreate
from services.auth_service import authenticate, create_session, revoke_session, set_password
from services.membership_service import create_user, list_user_projects, require_project_member
from services.project_service import create_project


def _project(name, owner_id, session):
    return create_project(
        ProjectCreate(
            name=name,
            product_name="测试产品",
            access_code="secure-2026",
            markets=["DE"],
        ),
        owner_user_id=owner_id,
        session=session,
    )


def test_unverified_user_cannot_authenticate(db_session):
    user = create_user(
        "待验证用户",
        "pending@example.test",
        email_verified=False,
        session=db_session,
    )
    set_password(user.id, "secure-password", session=db_session)
    with pytest.raises(ProjectAccessDeniedError):
        authenticate("pending@example.test", "secure-password", session=db_session)


def test_session_revocation_blocks_follow_up_access(db_session):
    user = create_user("会话用户", "session@example.test", session=db_session)
    set_password(user.id, "secure-password", session=db_session)
    token = create_session(user.id, session=db_session)
    revoke_session(token, session=db_session)
    with pytest.raises(ProjectAccessDeniedError):
        from services.auth_service import resolve_session

        resolve_session(token, session=db_session)
    assert db_session.scalar(select(AuthSession).where(AuthSession.user_id == user.id)).revoked_at


def test_authenticated_user_cannot_switch_project_without_membership(db_session):
    owner = create_user("项目一负责人", "one@example.test", session=db_session)
    other = create_user("项目二负责人", "two@example.test", session=db_session)
    first = _project("项目一", owner.id, db_session)
    second = _project("项目二", other.id, db_session)
    assert [item.id for item in list_user_projects(owner.id, session=db_session)] == [first.id]
    with pytest.raises(ProjectAccessDeniedError):
        require_project_member(second.id, owner.id, session=db_session)
