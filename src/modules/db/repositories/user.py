"""User repository."""

from __future__ import annotations

from sqlalchemy import select

from ..models.user import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def count_users(self) -> int:
        return await self.count()
