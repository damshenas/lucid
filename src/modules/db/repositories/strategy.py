"""Strategy registry repository."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from ..models.strategy import StrategyRegistry
from .base import BaseRepository


class StrategyRepository(BaseRepository[StrategyRegistry]):
    model = StrategyRegistry

    async def get_by_name(self, name: str) -> StrategyRegistry | None:
        stmt = select(StrategyRegistry).where(StrategyRegistry.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_direction(self, direction: str) -> list[StrategyRegistry]:
        stmt = select(StrategyRegistry).where(StrategyRegistry.direction == direction)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        name: str,
        file_path: str,
        direction: str,
        is_builtin: bool = False,
        version: str | None = None,
        description: str | None = None,
    ) -> StrategyRegistry:
        now = datetime.now(timezone.utc)
        existing = await self.get_by_name(name)
        if existing is not None:
            existing.file_path = file_path
            existing.direction = direction
            existing.is_builtin = is_builtin
            existing.version = version
            existing.description = description
            existing.last_scanned_at = now
            await self.session.flush()
            return existing
        return await self.create(
            name=name,
            file_path=file_path,
            direction=direction,
            is_builtin=is_builtin,
            version=version,
            description=description,
            last_scanned_at=now,
        )

    async def delete_missing(self, current_names: set[str]) -> list[str]:
        """Delete registry rows whose name is no longer among currently discovered
        strategies (e.g. a file's ``STRATEGY_NAME`` was renamed, or the file itself was
        removed) — without this, a rename leaves the old name permanently listed
        alongside the new one. Returns the removed names."""
        stale = [row for row in await self.get_all() if row.name not in current_names]
        for row in stale:
            await self.session.delete(row)
        if stale:
            await self.session.flush()
        return [row.name for row in stale]
