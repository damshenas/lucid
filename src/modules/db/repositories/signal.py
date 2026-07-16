"""Signal and signal-outcome repositories."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

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

    async def list_by_user(
        self, user_id: int, *, limit: int = 50, offset: int = 0, source: str | None = None
    ) -> list[Signal]:
        stmt = select(Signal).where(Signal.user_id == user_id)
        if source is not None:
            stmt = stmt.where(Signal.source == source)
        stmt = stmt.order_by(Signal.id.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_all_for_user(self, user_id: int) -> int:
        """Hard-delete every signal for a user — used by the admin "reset trading
        data" endpoint (src/api/v1/admin.py). Caller must delete the user's
        ``signal_outcomes`` rows first (see SignalOutcomeRepository.delete_all_for_user)
        since they reference ``signals.id``. Returns the number of rows removed."""
        result = await self.session.execute(delete(Signal).where(Signal.user_id == user_id))
        await self.session.flush()
        return int(result.rowcount or 0)


class SignalOutcomeRepository(BaseRepository[SignalOutcome]):
    model = SignalOutcome

    async def delete_all_for_user(self, user_id: int) -> int:
        """Hard-delete every signal outcome for a user — used by the admin "reset
        trading data" endpoint (src/api/v1/admin.py). Returns the number of rows
        removed."""
        result = await self.session.execute(
            delete(SignalOutcome).where(SignalOutcome.user_id == user_id)
        )
        await self.session.flush()
        return int(result.rowcount or 0)
