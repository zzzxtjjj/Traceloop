import hashlib
import hmac
import json
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.db import session_context, session_scope
from core.errors import ProjectAccessDeniedError
from core.models import AuditEvent, Project, ProjectMember, User
from core.schemas import ProjectCreate


class ProjectNameExistsError(ValueError):
    pass


def _hash_access_code(access_code: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", access_code.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_access_code(access_code: str, encoded: str) -> bool:
    algorithm, salt_hex, digest_hex = encoded.split("$", maxsplit=2)
    if algorithm != "pbkdf2_sha256":
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", access_code.encode("utf-8"), bytes.fromhex(salt_hex), 200_000
    )
    return hmac.compare_digest(actual.hex(), digest_hex)


def create_project(
    payload: ProjectCreate,
    owner_user_id: int | None = None,
    session: Session | None = None,
) -> Project:
    with session_context(session) as db:
        if db.scalar(select(Project.id).where(Project.name == payload.name)) is not None:
            raise ProjectNameExistsError("项目名称已存在，请换一个名称。")
        if owner_user_id is not None:
            owner = db.get(User, owner_user_id)
            if not owner or not owner.active:
                raise ProjectAccessDeniedError("当前用户无权执行该项目操作。")
        project = Project(
            name=payload.name,
            product_name=payload.product_name,
            access_code_hash=_hash_access_code(payload.access_code),
            markets_json=json.dumps(payload.markets, ensure_ascii=False),
        )
        try:
            with db.begin_nested():
                db.add(project)
                db.flush()
                if owner_user_id is not None:
                    db.add(
                        ProjectMember(
                            project_id=project.id,
                            user_id=owner_user_id,
                            role="owner",
                            status="active",
                        )
                    )
                db.add(
                    AuditEvent(
                        project_id=project.id,
                        actor_role="owner" if owner_user_id is not None else "项目负责人",
                        action="project_created",
                        entity_type="project",
                        entity_id=project.id,
                    )
                )
                db.flush()
        except IntegrityError as exc:
            raise ProjectNameExistsError("项目名称已存在，请换一个名称。") from exc
        return project


def list_projects() -> list[Project]:
    with session_scope() as session:
        return list(session.scalars(select(Project).order_by(Project.created_at.desc())))


def get_project(project_id: int) -> Project | None:
    with session_scope() as session:
        return session.get(Project, project_id)


def get_project_by_name(name: str) -> Project | None:
    with session_scope() as session:
        return session.scalar(select(Project).where(Project.name == name))


def verify_project_access(project_id: int, access_code: str) -> bool:
    project = get_project(project_id)
    if not project:
        return False
    return verify_access_code(access_code, project.access_code_hash)

