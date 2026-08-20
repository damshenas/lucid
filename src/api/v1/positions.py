"""Position routes: list open positions and sync from the broker."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.conf.schema import AssetClass
from src.modules.db.models.base import PositionStatus
from src.modules.db.models.user import User
from src.modules.db.repositories.position import PositionRepository

from ..context import AppContext
from ..deps import get_context, get_current_user, get_session

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])


def _serialize(position: Any) -> dict[str, Any]:
    return {
        "ticker": position.ticker,
        "quantity": position.quantity,
        "avg_price": position.avg_price,
        "asset_class": position.asset_class,
        "status": position.status,
    }


async def sync_positions_from_broker(
    ctx: AppContext, session: AsyncSession, user_id: int, asset_class: str
) -> dict[str, int]:
    """Fetch a user's current broker positions and reconcile them into the local
    ``positions`` table: create/update anything the broker reports, and close any
    locally-open position the broker no longer reports. Shared by ``POST
    /api/v1/positions/sync`` (self-service) and the admin "reset trading data"
    endpoint (``src/api/v1/admin.py``), which calls this right after wiping a user's
    trade history so positions start fresh from whatever the broker actually holds."""
    broker = await ctx.resolve_broker(session, user_id, asset_class)
    broker_positions = await broker.get_positions()

    repo = PositionRepository(session)
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    for bp in broker_positions:
        seen.add(bp.ticker)
        existing = await repo.get_open_by_ticker(user_id, bp.ticker)
        if existing is None:
            await repo.create(
                user_id=user_id,
                ticker=bp.ticker,
                asset_class=asset_class,
                quantity=bp.quantity,
                avg_price=bp.avg_price,
                status=PositionStatus.open.value,
                opened_at=now,
            )
        else:
            await repo.update(existing, quantity=bp.quantity, avg_price=bp.avg_price)

    # Close local open positions the broker no longer reports — scoped to this
    # asset_class only. list_open() returns a user's open positions across every
    # asset class (equity/crypto/fx/commodity can each have their own broker), so
    # without this filter a sync of one asset class would wrongly close open
    # positions that simply belong to a *different* asset class and were never
    # queried from this broker at all.
    closed = 0
    for local in await repo.list_open(user_id):
        if local.asset_class != asset_class:
            continue
        if local.ticker not in seen:
            await repo.update(
                local, quantity=0.0, status=PositionStatus.closed.value, closed_at=now
            )
            closed += 1

    return {"synced": len(broker_positions), "closed": closed}


@router.get("")
async def list_positions(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    positions = await PositionRepository(session).list_open(user.id)
    return [_serialize(p) for p in positions]


@router.post("/sync")
async def sync_positions(
    request: Request,
    asset_class: str = AssetClass.equity.value,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    ctx = get_context(request)
    result = await sync_positions_from_broker(ctx, session, user.id, asset_class)
    await session.commit()
    return result

