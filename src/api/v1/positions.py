"""Position routes: list open positions and sync from the broker."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.conf.schema import AssetClass
from src.modules.bus import BrokerSyncEvent
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
    locally-open position the broker no longer reports — the broker is always the
    source of truth. Shared by ``POST /api/v1/positions/sync`` (self-service), the
    admin "reset trading data" endpoint (``src/api/v1/admin.py``), and the periodic
    ``sync_broker_positions`` job (``src/api/runtime.py``). Publishes one
    ``BrokerSyncEvent`` with whatever was created/adjusted/closed, only when this
    call actually changed something."""
    broker = await ctx.resolve_broker(session, user_id, asset_class)
    broker_positions = await broker.get_positions()

    repo = PositionRepository(session)
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    created: list[str] = []
    adjusted: list[str] = []
    for bp in broker_positions:
        seen.add(bp.ticker)
        existing = await repo.get_open_by_ticker(user_id, bp.ticker, asset_class)
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
            created.append(bp.ticker)
        elif (
            abs(existing.quantity - bp.quantity) > 1e-9
            or abs(existing.avg_price - bp.avg_price) > 1e-9
        ):
            await repo.update(existing, quantity=bp.quantity, avg_price=bp.avg_price)
            adjusted.append(bp.ticker)

    # Close local open positions the broker no longer reports — scoped to this
    # asset_class only. list_open() returns a user's open positions across every
    # asset class (equity/crypto/fx/commodity can each have their own broker), so
    # without this filter a sync of one asset class would wrongly close open
    # positions that simply belong to a *different* asset class and were never
    # queried from this broker at all.
    closed: list[str] = []
    for local in await repo.list_open(user_id):
        if local.asset_class != asset_class:
            continue
        if local.ticker not in seen:
            await repo.update(
                local, quantity=0.0, status=PositionStatus.closed.value, closed_at=now
            )
            closed.append(local.ticker)

    if created or adjusted or closed:
        await ctx.bus.publish(
            BrokerSyncEvent(
                user_id=user_id,
                asset_class=asset_class,
                created=created,
                adjusted=adjusted,
                closed=closed,
            )
        )

    return {"synced": len(broker_positions), "closed": len(closed)}



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

