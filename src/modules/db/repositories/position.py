"""Position repository."""

from __future__ import annotations

from sqlalchemy import select

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
