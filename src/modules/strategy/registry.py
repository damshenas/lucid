"""Strategy registry service: scan files into the DB, list, and resolve active strategies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.modules.db.models.strategy import StrategyRegistry
from src.modules.db.repositories.strategy import StrategyRepository

from .loader import LoadedStrategy, discover_strategies

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def build_extra_sections(
    strategies: list[LoadedStrategy],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Map active strategies to config sections for ``ConfigService.compile_schema``."""
    return {f"strategy.{s.name}": s.config_schema for s in strategies}


class StrategyRegistryService:
    def __init__(self, session: AsyncSession, strategies_root: str) -> None:
        self._repo = StrategyRepository(session)
        self._root = strategies_root
        self._cache: dict[str, LoadedStrategy] | None = None

    def _discover(self) -> dict[str, LoadedStrategy]:
        if self._cache is None:
            self._cache = {s.name: s for s in discover_strategies(self._root)}
        return self._cache

    def invalidate(self) -> None:
        self._cache = None

    async def scan(self) -> list[StrategyRegistry]:
        self.invalidate()
        rows: list[StrategyRegistry] = []
        for strategy in self._discover().values():
            rows.append(
                await self._repo.upsert(
                    name=strategy.name,
                    file_path=strategy.file_path,
                    direction=strategy.direction,
                    is_builtin=strategy.is_builtin,
                    version=strategy.version,
                    description=strategy.description,
                )
            )
        return rows

    async def list(self, direction: str | None = None) -> list[StrategyRegistry]:
        if direction is None:
            return await self._repo.get_all()
        return await self._repo.list_by_direction(direction)

    def get_loaded(self, name: str) -> LoadedStrategy | None:
        return self._discover().get(name)

    def get_active(
        self, config_values: dict[str, Any], direction: str
    ) -> LoadedStrategy | None:
        name = (config_values.get("strategy") or {}).get(f"active_{direction}_strategy")
        if not name:
            return None
        return self.get_loaded(name)

    def active_extra_sections(
        self, config_values: dict[str, Any]
    ) -> dict[str, dict[str, dict[str, Any]]]:
        active = [
            s
            for s in (
                self.get_active(config_values, "buy"),
                self.get_active(config_values, "sell"),
            )
            if s is not None
        ]
        return build_extra_sections(active)

    def all_extra_sections(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Config sections for every discovered strategy, active or not.

        Used by the settings UI so admins/traders can browse and activate any
        available strategy, not only whichever one already happens to be active.
        """
        return build_extra_sections(list(self._discover().values()))


__all__ = ["StrategyRegistryService", "build_extra_sections"]
