"""Signal and signal-outcome repositories."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..models.base import SignalStatus
from ..models.signal import Signal, SignalOutcome
from .base import BaseRepository


class SignalRepository(BaseRepository[Signal]):
    model = Signal

    async def recent_for_ticker(
        self, user_id: int, ticker: str, direction: str, within_seconds: int
    ) -> Signal | None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
        stmt = (
            select(Signal)
            .where(
                Signal.user_id == user_id,
                Signal.ticker == ticker,
                Signal.direction == direction,
                Signal.status == SignalStatus.acted.value,
                Signal.acted_at.is_not(None),
                Signal.acted_at >= cutoff,
            )
            .order_by(Signal.acted_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_user(self, user_id: int, *, limit: int = 50, offset: int = 0) -> list[Signal]:
        stmt = (
            select(Signal)
            .where(Signal.user_id == user_id)
            .order_by(Signal.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class SignalOutcomeRepository(BaseRepository[SignalOutcome]):
    model = SignalOutcome
