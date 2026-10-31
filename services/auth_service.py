"""Password and server-side session primitives for the V1 backend."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import ProjectAccessDeniedError
from core.models import AuthSession, ProjectMember, User, utc_now

PASSWORD_ITERATIONS = 200_000
SESSION_TTL = timedelta(hours=12)


def _password_hash(password: str) -> str:
    value = password.strip()
    if len(value) < 8:
        raise ValueError("密码至少需要 8 个字符。")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str | None) -> bool:
    if not encoded or not encoded.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual.hex(), digest_hex)


def set_password(user_id: int, password: str, session: Session | None = None) -> User:
    with session_context(session) as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise ProjectAccessDeniedError("用户不存在或已停用。")
        user.password_hash = _password_hash(password)
        db.flush()
        return user


def authenticate(email: str, password: str, session: Session | None = None) -> User:
    normalized = email.strip().casefold()
    with session_context(session) as db:
        user = db.scalar(select(User).where(User.email == normalized, User.active.is_(True)))
        if not user or not _verify_password(password, user.password_hash):
            raise ProjectAccessDeniedError("邮箱或密码不正确。")
        return user


def create_session(
    user_id: int,
    *,
    session: Session | None = None,
    ttl: timedelta = SESSION_TTL,
) -> str:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = utc_now()
    with session_context(session) as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise ProjectAccessDeniedError("用户不存在或已停用。")
        db.add(
            AuthSession(
                user_id=user_id,
                token_hash=token_hash,
                created_at=now,
                last_seen_at=now,
                expires_at=now + ttl,
            )
        )
        db.flush()
    return raw_token


def resolve_session(token: str, session: Session | None = None) -> User:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = utc_now()
    with session_context(session) as db:
        auth = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        if not auth:
            raise ProjectAccessDeniedError("登录会话无效或已过期。")
        user = db.scalar(select(User).where(User.id == auth.user_id, User.active.is_(True)))
        if not user:
            raise ProjectAccessDeniedError("登录会话无效或已过期。")
        auth.last_seen_at = now
        db.flush()
        return user


def revoke_session(token: str, session: Session | None = None) -> None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with session_context(session) as db:
        auth = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
        if auth:
            auth.revoked_at = utc_now()
            db.flush()


def require_session_member(
    token: str,
    project_id: int,
    session: Session | None = None,
) -> tuple[User, ProjectMember]:
    """Resolve actor and active membership from the server-side session record."""
    with session_context(session) as db:
        user = resolve_session(token, session=db)
        membership = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
                ProjectMember.status == "active",
            )
        )
        if not membership:
            raise ProjectAccessDeniedError("当前账号无权访问该项目。")
        return user, membership
