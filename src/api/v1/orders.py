"""Order read routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.db.models.user import User
from src.modules.db.repositories.order import OrderRepository

from ..deps import get_current_user, get_session

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


@router.get("")
async def list_orders(
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    orders = await OrderRepository(session).list_by_user(user.id, limit=limit, offset=offset)
    return [
        {
            "ticker": o.ticker,
            "side": o.side,
            "quantity": o.quantity,
            "price": o.price,
            "status": o.status,
            "paper": o.paper,
        }
        for o in orders
    ]
