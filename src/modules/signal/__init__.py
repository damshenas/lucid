"""Signal lifecycle: store, dedup, mark acted/blocked, and record outcomes.

No scraping or external data — just persistence and dedup. Dedup suppresses a signal for
the same ``(user, ticker, direction)`` if one was already acted on within a configurable
window. A TTL cache short-circuits the DB check when provided.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.conf.schema import AssetClass
from src.modules.bus import BuySignalEvent, SellSignalEvent
from src.modules.db.models.base import Direction, SignalStatus
from src.modules.db.models.signal import Signal
from src.modules.db.repositories.signal import SignalOutcomeRepository, SignalRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.modules.cache import TTLCache


class SignalService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        cache: TTLCache | None = None,
        dedup_window_seconds: int = 300,
    ) -> None:
        self._repo = SignalRepository(session)
        self._outcomes = SignalOutcomeRepository(session)
        self._cache = cache
        self._window = dedup_window_seconds

    @staticmethod
    def _key(user_id: int, ticker: str, direction: str) -> str:
        return f"sig:{user_id}:{ticker}:{direction}"

    async def store(
        self,
        *,
        user_id: int,
        ticker: str,
        direction: str,
        source: str,
        asset_class: str = AssetClass.equity.value,
        confidence: float | None = None,
        reasoning: str | None = None,
    ) -> Signal:
        return await self._repo.create(
            user_id=user_id,
            ticker=ticker,
            direction=direction,
            source=source,
            asset_class=asset_class,
            confidence=confidence,
            reasoning=reasoning,
            status=SignalStatus.new.value,
        )

    async def store_from_event(self, event: BuySignalEvent | SellSignalEvent) -> Signal:
        direction = (
            Direction.buy.value if isinstance(event, BuySignalEvent) else Direction.sell.value
        )
        return await self.store(
            user_id=event.user_id,
            ticker=event.ticker,
            direction=direction,
            source=event.source,
            asset_class=event.asset_class,
            confidence=event.confidence,
            reasoning=event.reasoning,
        )

    async def is_duplicate(self, user_id: int, ticker: str, direction: str) -> bool:
        if self._cache is not None and self._key(user_id, ticker, direction) in self._cache:
            return True
        recent = await self._repo.recent_for_ticker(user_id, ticker, direction, self._window)
        return recent is not None

    async def mark_acted(self, signal: Signal) -> Signal:
        updated = await self._repo.update(
            signal, status=SignalStatus.acted.value, acted_at=datetime.now(timezone.utc)
        )
        if self._cache is not None:
            self._cache.set(
                self._key(signal.user_id, signal.ticker, signal.direction), True, self._window
            )
        return updated

    async def mark_blocked(self, signal: Signal) -> Signal:
        return await self._repo.update(signal, status=SignalStatus.blocked.value)

    async def record_outcome(
        self,
        *,
        signal_id: int,
        user_id: int,
        pnl: float,
        closed_at: datetime | None = None,
    ) -> None:
        await self._outcomes.create(
            signal_id=signal_id,
            user_id=user_id,
            pnl=pnl,
            profitable=pnl > 0,
            closed_at=closed_at or datetime.now(timezone.utc),
        )


__all__ = ["SignalService"]
