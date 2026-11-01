import hashlib

import pytest
from sqlalchemy import select

from core.errors import ProjectAccessDeniedError
from core.models import AuthThrottle, User
from services.auth_service import (
    authenticate,
    create_session,
    issue_email_verification,
    reset_password_with_code,
    resolve_session,
    set_password,
    verify_email,
)
from services.membership_service import create_user


def test_failed_passwords_lock_and_do_not_strip_password(db_session):
    user = create_user('Throttle', 'throttle@example.test', session=db_session)
    set_password(user.id, ' spaced-password ', session=db_session)
    for _ in range(5):
        with pytest.raises(ProjectAccessDeniedError):
            authenticate(user.email, 'spaced-password', session=db_session)
    throttle = db_session.get(AuthThrottle, hashlib.sha256(user.email.encode()).hexdigest())
    assert throttle.failures == 5
    assert throttle.locked_until is not None
    with pytest.raises(ProjectAccessDeniedError):
        authenticate(user.email, ' spaced-password ', session=db_session)


def test_wrong_codes_count_and_reset_revokes_sessions(db_session):
    user = create_user('Reset', 'reset@example.test', session=db_session)
    set_password(user.id, 'old-password', session=db_session)
    token = create_session(user.id, session=db_session)
    code = issue_email_verification(user.id, session=db_session)
    with pytest.raises(ValueError):
        reset_password_with_code(user.id, 'invalid', 'new-password', session=db_session)
    assert user.email_verification_attempts == 1
    reset_password_with_code(user.id, code, 'new-password', session=db_session)
    assert authenticate(user.email, 'new-password', session=db_session).id == user.id
    with pytest.raises(ProjectAccessDeniedError):
        resolve_session(token, session=db_session)
    assert db_session.scalar(select(User).where(User.id == user.id)).email_verified


def test_unverified_wrong_code_does_not_verify(db_session):
    user = create_user('Pending', 'pending-code@example.test',
                       email_verified=False, session=db_session)
    issue_email_verification(user.id, session=db_session)
    for _ in range(5):
        with pytest.raises(ValueError):
            verify_email(user.id, 'invalid', session=db_session)
    assert not user.email_verified
    assert user.email_verification_attempts == 5
    with pytest.raises(ProjectAccessDeniedError):
        create_session(user.id, session=db_session)
