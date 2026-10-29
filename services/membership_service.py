from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import ProjectAccessDeniedError
from core.models import AuditEvent, Project, ProjectMember, User

PROJECT_ROLES = {"owner", "procurement", "operations", "quality"}
ACTIVE_MEMBERSHIP = "active"
DENIED_MESSAGE = "当前用户无权执行该项目操作。"


class UserEmailExistsError(ValueError):
    pass


def _normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValueError("请输入有效的用户邮箱。")
    return normalized


def create_user(
    display_name: str,
    email: str,
    *,
    active: bool = True,
    session: Session | None = None,
) -> User:
    name = display_name.strip()
    if not name:
        raise ValueError("用户显示名称不能为空。")
    normalized_email = _normalize_email(email)
    with session_context(session) as db:
        if db.scalar(select(User.id).where(User.email == normalized_email)) is not None:
            raise UserEmailExistsError("用户邮箱已存在。")
        user = User(display_name=name, email=normalized_email, active=active)
        try:
            with db.begin_nested():
                db.add(user)
                db.flush()
        except IntegrityError as exc:
            raise UserEmailExistsError("用户邮箱已存在。") from exc
        return user


def get_user_by_email(email: str, session: Session | None = None) -> User | None:
    normalized = _normalize_email(email)
    with session_context(session) as db:
        return db.scalar(select(User).where(User.email == normalized))


def list_users(
    *, include_inactive: bool = False, session: Session | None = None
) -> list[User]:
    with session_context(session) as db:
        statement = select(User)
        if not include_inactive:
            statement = statement.where(User.active.is_(True))
        return list(db.scalars(statement.order_by(User.display_name, User.id)))


def list_user_projects(user_id: int, session: Session | None = None) -> list[Project]:
    with session_context(session) as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            return []
        return list(
            db.scalars(
                select(Project)
                .join(ProjectMember, ProjectMember.project_id == Project.id)
                .where(
                    ProjectMember.user_id == user_id,
                    ProjectMember.status == ACTIVE_MEMBERSHIP,
                )
                .order_by(Project.created_at.desc())
            )
        )


def require_project_member(
    project_id: int, user_id: int, session: Session | None = None
) -> ProjectMember:
    with session_context(session) as db:
        membership = db.scalar(
            select(ProjectMember)
            .join(User, User.id == ProjectMember.user_id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.status == ACTIVE_MEMBERSHIP,
                User.active.is_(True),
            )
        )
        if not membership:
            raise ProjectAccessDeniedError(DENIED_MESSAGE)
        return membership


def require_project_role(
    project_id: int,
    user_id: int,
    allowed_roles: Iterable[str],
    session: Session | None = None,
) -> ProjectMember:
    allowed = set(allowed_roles)
    membership = require_project_member(project_id, user_id, session=session)
    if membership.role not in allowed:
        raise ProjectAccessDeniedError(DENIED_MESSAGE)
    return membership


def list_project_members(
    project_id: int,
    requester_user_id: int,
    session: Session | None = None,
) -> list[ProjectMember]:
    with session_context(session) as db:
        require_project_member(project_id, requester_user_id, session=db)
        return list(
            db.scalars(
                select(ProjectMember)
                .where(ProjectMember.project_id == project_id)
                .order_by(ProjectMember.created_at, ProjectMember.id)
            )
        )


def bootstrap_project_owner(
    project_id: int,
    user_id: int,
    session: Session | None = None,
) -> ProjectMember:
    """Assign the first owner for a legacy project that has no owner membership."""
    with session_context(session) as db:
        project = db.get(Project, project_id)
        user = db.get(User, user_id)
        if not project or not user or not user.active:
            raise ProjectAccessDeniedError(DENIED_MESSAGE)
        existing_owner = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == "owner",
                ProjectMember.status == ACTIVE_MEMBERSHIP,
            )
        )
        if existing_owner:
            if existing_owner.user_id == user_id:
                return existing_owner
            raise ProjectAccessDeniedError(DENIED_MESSAGE)
        membership = ProjectMember(
            project_id=project_id,
            user_id=user_id,
            role="owner",
            status=ACTIVE_MEMBERSHIP,
        )
        db.add(membership)
        db.flush()
        return membership

def add_project_member(
    project_id: int,
    owner_user_id: int,
    user_id: int,
    role: str,
    session: Session | None = None,
) -> ProjectMember:
    if role not in PROJECT_ROLES:
        raise ValueError("无效的项目成员角色。")
    with session_context(session) as db:
        require_project_role(project_id, owner_user_id, {"owner"}, session=db)
        target_user = db.get(User, user_id)
        if not target_user or not target_user.active:
            raise ValueError("目标用户不存在或已停用。")
        existing = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        if existing:
            if existing.role == role and existing.status == ACTIVE_MEMBERSHIP:
                return existing
            raise ValueError("该用户已是项目成员；请使用受保护的成员更新流程。")
        membership = ProjectMember(
            project_id=project_id,
            user_id=user_id,
            role=role,
            status=ACTIVE_MEMBERSHIP,
        )
        db.add(membership)
        db.flush()
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role="owner",
                action="project_member_added",
                entity_type="project_member",
                entity_id=membership.id,
            )
        )
        db.flush()
        return membership

