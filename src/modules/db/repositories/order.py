"""Order repository."""

from __future__ import annotations

from sqlalchemy import delete, select

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

    async def delete_all_for_user(self, user_id: int) -> int:
        """Hard-delete every order for a user — used by the admin "reset trading
        data" endpoint (src/api/v1/admin.py). Returns the number of rows removed."""
        result = await self.session.execute(delete(Order).where(Order.user_id == user_id))
        await self.session.flush()
        return int(result.rowcount or 0)

