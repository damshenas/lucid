"""Authentication service: user bootstrap, login, password changes.

First-run rule: if no users exist, ``bootstrap_first_admin`` creates the initial admin
without requiring auth. Once any user exists, it refuses — callers must go through normal
authenticated user creation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.db.models.base import Role
from src.modules.db.models.user import User
from src.modules.db.repositories.user import UserRepository

from .password import hash_password, verify_password

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AuthError(Exception):
    """Base authentication error."""


class InvalidCredentialsError(AuthError):
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
        return await self._users.create(
            username=username,
            password_hash=hash_password(password),
            role=Role.admin.value,
            must_change_password=False,
            is_active=True,
        )

    async def create_user(
        self, username: str, password: str, role: str = Role.viewer.value
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
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("invalid username or password")
        return user

    async def change_password(self, user: User, new_password: str) -> User:
        return await self._users.update(
            user,
            password_hash=hash_password(new_password),
            must_change_password=False,
        )
