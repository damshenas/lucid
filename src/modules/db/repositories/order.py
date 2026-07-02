"""Order repository."""

from __future__ import annotations

from sqlalchemy import select

from ..models.order import Order
from .base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    model = Order

    async def list_by_user(self, user_id: int, *, limit: int = 50, offset: int = 0) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

