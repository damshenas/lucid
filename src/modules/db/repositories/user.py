"""User repository."""

from __future__ import annotations

from sqlalchemy import select, update

from ..models.user import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def count_users(self) -> int:
        return await self.count()

    async def increment_failed_attempts(self, user_id: int) -> int:
        """Atomically ``SET failed_login_attempts = failed_login_attempts + 1`` and
        return the new value — a single DB-side statement, not a python-level
        read-then-write, so concurrent wrong-password requests for the same user
        can't lose updates against each other (bugs.md finding 9)."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(failed_login_attempts=User.failed_login_attempts + 1)
            .returning(User.failed_login_attempts)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()
