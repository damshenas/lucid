"""Order repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from ..models.base import OrderSide
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

    async def total_buy_usd_since(self, user_id: int, since: datetime) -> float:
        stmt = select(func.coalesce(func.sum(Order.quantity * Order.price), 0.0)).where(
            Order.user_id == user_id,
            Order.side == OrderSide.buy.value,
            Order.price.is_not(None),
            Order.created_at >= since,
        )
        result = await self.session.execute(stmt)
        return float(result.scalar_one())

