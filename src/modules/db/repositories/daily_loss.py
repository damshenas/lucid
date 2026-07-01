"""Daily-loss repository (used by the optional risk gate)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from ..models.risk import DailyLoss
from .base import BaseRepository


class DailyLossRepository(BaseRepository[DailyLoss]):
    model = DailyLoss

    async def get_for_day(self, user_id: int, day: date) -> DailyLoss | None:
        stmt = select(DailyLoss).where(DailyLoss.user_id == user_id, DailyLoss.day == day)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_loss(self, user_id: int, day: date, amount: float) -> DailyLoss:
        row = await self.get_for_day(user_id, day)
        if row is None:
            return await self.create(user_id=user_id, day=day, loss_usd=amount)
        row.loss_usd += amount
        await self.session.flush()
        return row
