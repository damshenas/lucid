"""Position repository."""

from __future__ import annotations

from sqlalchemy import delete, select

from ..models.base import PositionStatus
from ..models.position import Position
from .base import BaseRepository


class PositionRepository(BaseRepository[Position]):
    model = Position

    async def get_open_by_ticker(self, user_id: int, ticker: str) -> Position | None:
        stmt = select(Position).where(
            Position.user_id == user_id,
            Position.ticker == ticker,
            Position.status == PositionStatus.open.value,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_open(self, user_id: int) -> list[Position]:
        stmt = select(Position).where(
            Position.user_id == user_id,
            Position.status == PositionStatus.open.value,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_open(self) -> list[Position]:
        """Every open position across every user — used to (a) evaluate sell
        strategies against held tickers regardless of the (buy-only) price watchlist,
        and (b) keep those tickers' price bars fetched even if removed from the
        watchlist (see TradingRuntime.run_strategies / ._watchlist in src/api/runtime.py)."""
        stmt = select(Position).where(Position.status == PositionStatus.open.value)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_tier_taken(self, position: Position, tier: int) -> Position:
        """Flip ``profit_tier{tier}_taken`` so a tiered sell strategy (e.g.
        trailing_stop) never re-fires the same profit-take tier again for this
        position. ``tier`` must be 1 or 2."""
        if tier not in (1, 2):
            raise ValueError(f"invalid profit tier {tier!r}; must be 1 or 2")
        return await self.update(position, **{f"profit_tier{tier}_taken": True})

    async def delete_all_for_user(self, user_id: int) -> int:
        """Hard-delete every position (open or closed) for a user — used by the admin
        "reset trading data" endpoint (src/api/v1/admin.py) to wipe history before a
        fresh broker sync. Returns the number of rows removed."""
        result = await self.session.execute(delete(Position).where(Position.user_id == user_id))
        await self.session.flush()
        return int(result.rowcount or 0)
