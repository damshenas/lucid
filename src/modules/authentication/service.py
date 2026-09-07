"""Authentication service: user bootstrap, login, password changes.

First-run rule: if no users exist, ``bootstrap_first_admin`` creates the initial admin
without requiring auth. Once any user exists, it refuses — callers must go through normal
authenticated user creation.

Login lockout: after ``MAX_FAILED_ATTEMPTS`` consecutive failed logins for a username,
further attempts are rejected for ``LOCKOUT_MINUTES`` even with the correct password,
to slow down credential-guessing against ``/login`` (the only unauthenticated boundary
besides first-run ``/setup``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from src.modules.db.models.base import Role
from src.modules.db.models.bootstrap import BootstrapLock
from src.modules.db.models.user import User
from src.modules.db.repositories.user import UserRepository

from .password import hash_password, verify_password

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class AuthError(Exception):
    """Base authentication error."""


class InvalidCredentialsError(AuthError):
    pass


class AccountLockedError(AuthError):
    pass


class FirstRunError(AuthError):
    pass


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)

    async def has_any_user(self) -> bool:
        return (await self._users.count_users()) > 0

    async def bootstrap_first_admin(self, username: str, password: str) -> User:
        if await self.has_any_user():
            raise FirstRunError("first admin already exists; bootstrap is locked")
        # The check above is a plain read then, further down, a write — two
        # concurrent first-run requests can both observe zero users before either
        # commits. Claiming this fixed-PK sentinel row in the same transaction is
        # what actually serializes them: whichever request's insert commits first
        # wins, the other gets a database-level integrity error here instead of both
        # successfully becoming admin (bugs.md finding 8).
        self._users.session.add(BootstrapLock(id=1))
        try:
            await self._users.session.flush()
        except IntegrityError as exc:
            raise FirstRunError("first admin already exists; bootstrap is locked") from exc
        return await self._users.create(
            username=username,
            password_hash=hash_password(password),
            role=Role.admin.value,
            must_change_password=False,
            is_active=True,
        )

    async def create_user(
        self, username: str, password: str, role: str = Role.analyst.value
    ) -> User:
        if await self._users.get_by_username(username) is not None:
            raise AuthError(f"username '{username}' already exists")
        return await self._users.create(
            username=username,
            password_hash=hash_password(password),
            role=role,
            must_change_password=True,
            is_active=True,
        )

    async def authenticate(self, username: str, password: str) -> User:
        user = await self._users.get_by_username(username)
        if user is None or not user.is_active:
            raise InvalidCredentialsError("invalid username or password")

        now = datetime.now(timezone.utc)
        locked_until = user.locked_until
        # SQLite (used in tests) doesn't persist tzinfo on DateTime(timezone=True)
        # columns, so a value we stored as aware UTC can come back naive. Treat any
        # naive value as UTC rather than comparing naive vs. aware, which raises.
        if locked_until is not None and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until is not None and locked_until > now:
            raise AccountLockedError(
                "account temporarily locked after too many failed login attempts"
            )

        if not verify_password(password, user.password_hash):
            # Atomic DB-side increment (SET x = x + 1), not a python-level
            # read-then-write — under concurrent wrong-password requests, a plain
            # `user.failed_login_attempts + 1` read-then-write can lose updates (two
            # requests both read 4, both write 5), letting far more than
            # MAX_FAILED_ATTEMPTS guesses through before locking (bugs.md finding 9).
            attempts = await self._users.increment_failed_attempts(user.id)
            if attempts >= MAX_FAILED_ATTEMPTS:
                await self._users.update(
                    user,
                    failed_login_attempts=0,
                    locked_until=now + timedelta(minutes=LOCKOUT_MINUTES),
                )
            raise InvalidCredentialsError("invalid username or password")

        if user.failed_login_attempts or user.locked_until is not None:
            await self._users.update(user, failed_login_attempts=0, locked_until=None)
        return user

    async def change_password(self, user: User, new_password: str) -> User:
        return await self._users.update(
            user,
            password_hash=hash_password(new_password),
            must_change_password=False,
        )
