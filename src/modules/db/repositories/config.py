"""Config-value repository. Handles scoped lookups and upserts across DB layers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..models.config import UserConfig
from .base import BaseRepository


class ConfigRepository(BaseRepository[UserConfig]):
    model = UserConfig

    @staticmethod
    def _scope_clause(user_id: int | None, asset_class: str | None):
        return (
            UserConfig.user_id.is_(None) if user_id is None else UserConfig.user_id == user_id,
            UserConfig.asset_class.is_(None)
            if asset_class is None
            else UserConfig.asset_class == asset_class,
        )

    async def get_scoped(
        self, key: str, *, user_id: int | None = None, asset_class: str | None = None
    ) -> UserConfig | None:
        stmt = select(UserConfig).where(UserConfig.key == key, *self._scope_clause(user_id, asset_class))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_scoped(
        self, *, user_id: int | None = None, asset_class: str | None = None
    ) -> list[UserConfig]:
        stmt = select(UserConfig).where(*self._scope_clause(user_id, asset_class))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_scoped(
        self,
        key: str,
        value: Any,
        *,
        user_id: int | None = None,
        asset_class: str | None = None,
    ) -> UserConfig:
        existing = await self.get_scoped(key, user_id=user_id, asset_class=asset_class)
        if existing is not None:
            existing.value = value
            await self.session.flush()
            return existing
        return await self.create(user_id=user_id, asset_class=asset_class, key=key, value=value)
