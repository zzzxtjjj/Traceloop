"""Password and server-side session primitives for the V1 backend."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import ProjectAccessDeniedError
from core.models import AuthSession, AuthThrottle, ProjectMember, User, utc_now

PASSWORD_ITERATIONS = 200_000
SESSION_TTL = timedelta(hours=12)
VERIFICATION_TTL = timedelta(minutes=15)
MAX_VERIFICATION_ATTEMPTS = 5
VERIFICATION_RESEND_INTERVAL = timedelta(minutes=1)


def _password_hash(password: str) -> str:
    value = password
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
        user.force_password_change = False
        db.flush()
        return user


def set_initial_password(user_id: int, password: str, session: Session | None = None) -> User:
    """Set an initial password while requiring a change at first login."""
    with session_context(session) as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise ProjectAccessDeniedError("用户不存在或已停用。")
        user.password_hash = _password_hash(password)
        user.force_password_change = True
        db.flush()
        return user


def issue_email_verification(user_id: int, session: Session | None = None) -> str:
    """Create a verification code; delivery is intentionally handled by deployment mail."""
    now = utc_now()
    with session_context(session) as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise ProjectAccessDeniedError("用户不存在或已停用。")
        if (
            user.email_verification_sent_at
            and now - user.email_verification_sent_at < VERIFICATION_RESEND_INTERVAL
        ):
            raise ValueError("验证码发送过于频繁，请稍后再试。")
        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        user.email_verification_expires_at = now + VERIFICATION_TTL
        user.email_verification_code_hash = code_hash
        user.email_verification_attempts = 0
        user.email_verification_sent_at = now
        db.flush()
        return code


def verify_email(user_id: int, code: str, session: Session | None = None) -> User:
    now = utc_now()
    with session_context(session) as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise ProjectAccessDeniedError("用户不存在或已停用。")
        if user.email_verified:
            return user
        if not user.email_verification_expires_at or user.email_verification_expires_at < now:
            raise ValueError("验证码已过期，请重新获取。")
        if user.email_verification_attempts >= MAX_VERIFICATION_ATTEMPTS:
            raise ValueError("验证码错误次数过多，请重新获取验证码。")
        user.email_verification_attempts += 1
        code_hash = hashlib.sha256(str(code).strip().encode("utf-8")).hexdigest()
        valid = bool(user.email_verification_code_hash) and hmac.compare_digest(
            code_hash, user.email_verification_code_hash
        )
        if valid:
            user.email_verified = True
            user.email_verification_attempts = 0
            user.email_verification_code_hash = None
        db.flush()
    if not valid:
        raise ValueError("验证码不正确。")
    return user


def verify_password_reset_code(user_id: int, code: str, session: Session | None = None) -> User:
    """Validate a reset code without changing an already verified email state."""
    now = utc_now()
    with session_context(session) as db:
        user = db.get(User, user_id)
        if not user or not user.active or not user.email_verified:
            raise ProjectAccessDeniedError("验证码不正确或已过期。")
        if not user.email_verification_expires_at or user.email_verification_expires_at < now:
            raise ValueError("验证码不正确或已过期。")
        if user.email_verification_attempts >= MAX_VERIFICATION_ATTEMPTS:
            raise ValueError("验证码错误次数过多，请重新获取验证码。")
        user.email_verification_attempts += 1
        code_hash = hashlib.sha256(str(code).strip().encode("utf-8")).hexdigest()
        valid = bool(user.email_verification_code_hash) and hmac.compare_digest(
            code_hash, user.email_verification_code_hash
        )
        if valid:
            user.email_verification_attempts = 0
            user.email_verification_code_hash = None
            user.email_verification_expires_at = None
        db.flush()
    if not valid:
        raise ValueError("验证码不正确或已过期。")
    return user


def authenticate(email: str, password: str, session: Session | None = None) -> User:
    normalized = email.strip().casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    failure = None
    with session_context(session) as db:
        now = utc_now()
        throttle = db.get(AuthThrottle, digest)
        if throttle and throttle.locked_until and throttle.locked_until > now:
            raise ProjectAccessDeniedError("登录尝试过于频繁，请稍后再试。")
        user = db.scalar(select(User).where(User.email == normalized, User.active.is_(True)))
        if not user or not _verify_password(password, user.password_hash):
            if throttle is None:
                throttle = AuthThrottle(email_digest=digest, failures=0)
                db.add(throttle)
            if throttle.locked_until and throttle.locked_until <= now:
                throttle.failures = 0
            throttle.failures += 1
            if throttle.failures >= 5:
                throttle.locked_until = now + timedelta(minutes=1)
            failure = ProjectAccessDeniedError("邮箱或密码不正确。")
        elif not user.email_verified:
            failure = ProjectAccessDeniedError("邮箱尚未验证，请先完成邮箱验证。")
        elif throttle:
            throttle.failures = 0
            throttle.locked_until = None
        db.flush()
    # Raise after the managed transaction commits, preserving failed-attempt counters.
    if failure:
        raise failure
    return user


def reset_password_with_code(user_id, code, password, session=None):
    """Consume reset challenge, change hash and revoke sessions atomically."""
    encoded = _password_hash(password)
    failure = None
    with session_context(session) as db:
        try:
            user = verify_password_reset_code(user_id, code, session=db)
        except (ValueError, ProjectAccessDeniedError) as exc:
            failure = exc
        else:
            user.password_hash = encoded
            user.force_password_change = False
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user_id)
                .values(revoked_at=utc_now())
            )
        db.flush()
    if failure:
        raise failure


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
        if not user or not user.active or not user.email_verified:
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
        if not user or not user.email_verified:
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
        if user.force_password_change:
            raise ProjectAccessDeniedError("请先修改初始密码。")
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
