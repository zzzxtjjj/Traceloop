from collections.abc import Iterable

from sqlalchemy.orm import Session

from core.errors import ProjectAccessDeniedError
from core.models import ProjectMember
from services.membership_service import require_project_member, require_project_role


def require_project_access(project_id: int, unlocked_project_ids: set[int] | list[int]) -> None:
    if project_id not in set(unlocked_project_ids):
        raise ProjectAccessDeniedError("当前会话无权访问该项目。")


def require_member_access(
    project_id: int,
    user_id: int,
    session: Session | None = None,
) -> ProjectMember:
    return require_project_member(project_id, user_id, session=session)


def require_role_access(
    project_id: int,
    user_id: int,
    allowed_roles: Iterable[str],
    session: Session | None = None,
) -> ProjectMember:
    return require_project_role(
        project_id,
        user_id,
        allowed_roles,
        session=session,
    )

