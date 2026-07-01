"""M2: authentication (bootstrap, login, tokens) and authorization (RBAC)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authentication import (
    AccountLockedError,
    AuthService,
    FirstRunError,
    InvalidCredentialsError,
    PasswordTooLongError,
    TokenError,
    TokenService,
    hash_password,
    verify_password,
)
from src.modules.authorization import (
    Permission,
    PermissionDenied,
    can_trade,
    has_permission,
    require_permission,
)


def test_password_hash_verify() -> None:
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h)
    assert not verify_password("wrong", h)


def test_hash_password_over_72_bytes_raises() -> None:
    with pytest.raises(PasswordTooLongError):
        hash_password("x" * 100)


def test_tokens_round_trip() -> None:
    svc = TokenService("secret", access_expiry_minutes=30)
    token = svc.create_access_token("42", role="trader")
    payload = svc.decode(token, expected_type="access")
    assert payload["sub"] == "42"
    assert payload["role"] == "trader"


def test_token_type_mismatch() -> None:
    svc = TokenService("secret")
    access = svc.create_access_token("1")
    with pytest.raises(TokenError):
        svc.decode(access, expected_type="refresh")


async def test_first_admin_bootstrap_then_lockdown(session: AsyncSession) -> None:
    svc = AuthService(session)
    assert not await svc.has_any_user()

    admin = await svc.bootstrap_first_admin("root", "pw")
    assert admin.role == "admin"
    assert admin.must_change_password is False

    with pytest.raises(FirstRunError):
        await svc.bootstrap_first_admin("root2", "pw")


async def test_authenticate(session: AsyncSession) -> None:
    svc = AuthService(session)
    await svc.bootstrap_first_admin("root", "pw")

    user = await svc.authenticate("root", "pw")
    assert user.username == "root"

    with pytest.raises(InvalidCredentialsError):
        await svc.authenticate("root", "bad")


async def test_created_user_must_change_password(session: AsyncSession) -> None:
    svc = AuthService(session)
    await svc.bootstrap_first_admin("root", "pw")
    user = await svc.create_user("viewer1", "pw", role="viewer")
    assert user.must_change_password is True

    updated = await svc.change_password(user, "newpw")
    assert updated.must_change_password is False


async def test_login_lockout_after_max_failed_attempts(session: AsyncSession) -> None:
    svc = AuthService(session)
    await svc.bootstrap_first_admin("root", "pw")

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            await svc.authenticate("root", "wrong")

    # 5th failure trips the lock, so even the correct password is now rejected.
    with pytest.raises(AccountLockedError):
        await svc.authenticate("root", "pw")


async def test_successful_login_resets_failed_attempts(session: AsyncSession) -> None:
    svc = AuthService(session)
    await svc.bootstrap_first_admin("root", "pw")

    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            await svc.authenticate("root", "wrong")

    user = await svc.authenticate("root", "pw")
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_rbac_matrix() -> None:
    assert can_trade("trader")
    assert not can_trade("admin")
    assert not can_trade("viewer")

    assert has_permission("admin", Permission.manage_users)
    assert not has_permission("trader", Permission.manage_users)

    assert has_permission("viewer", Permission.change_password)
    assert not has_permission("viewer", Permission.trade)

    require_permission("trader", Permission.trade)
    with pytest.raises(PermissionDenied):
        require_permission("viewer", Permission.trade)
