"""Order routes: read history and place manual (discretionary) orders."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.conf.schema import AssetClass
from src.modules.authorization import Permission
from src.modules.db.models.user import User
from src.modules.db.repositories.order import OrderRepository
from src.modules.execution import ManualOrderError

from ..deps import get_current_user, get_session, require_permission

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


class ManualOrderIn(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    asset_class: str = AssetClass.equity.value


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


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def place_manual_order(
    body: ManualOrderIn,
    request: Request,
    user: User = Depends(require_permission(Permission.trade)),
) -> dict[str, Any]:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "runtime not available")
    try:
        return await runtime.execution.place_manual_order(
            user_id=user.id,
            ticker=body.ticker.upper(),
            side=body.side,
            quantity=body.quantity,
            asset_class=body.asset_class,
        )
    except ManualOrderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
