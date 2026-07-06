"""Strategy routes: list, scan, per-user activation, and the decision log."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authorization import Permission
from src.modules.db.models.user import User
from src.modules.db.repositories.decision import StrategyDecisionRepository

from ..deps import get_context, get_current_user, get_session, require_permission

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


def _serialize(row: Any) -> dict[str, Any]:
    return {
        "name": row.name,
        "direction": row.direction,
        "version": row.version,
        "is_builtin": row.is_builtin,
        "description": row.description,
        "file_path": row.file_path,
        "features": row.features or [],
    }


@router.get("")
async def list_strategies(
    request: Request,
    direction: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    service = get_context(request).strategy_service(session)
    return [_serialize(r) for r in await service.list(direction)]


@router.post("/scan")
async def scan_strategies(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    service = get_context(request).strategy_service(session)
    rows = await service.scan()
    await session.commit()
    return {"scanned": len(rows)}


@router.patch("/{name}/activate")
async def activate_strategy(
    request: Request,
    name: str,
    direction: str = Query(..., pattern="^(buy|sell)$"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.edit_own_strategies)),
) -> dict[str, str]:
    ctx = get_context(request)
    service = ctx.strategy_service(session)
    if service.get_loaded(name) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"strategy '{name}' not found")
    await ctx.config_service(session).set_value(
        f"strategy.active_{direction}_strategy", name, role=user.role, user_id=user.id
    )
    await session.commit()
    return {"active": name, "direction": direction}


@router.get("/{name}/decisions")
async def list_decisions(
    name: str,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Every recorded change in this strategy's evaluation outcome for the current
    user — why it acted (bought/sold) or didn't, per ticker (see
    src/modules/db/models/decision.py, src/api/runtime.py, pages/StrategyDetail.tsx)."""
    rows = await StrategyDecisionRepository(session).list_by_strategy(
        user.id, name, limit=limit, offset=offset
    )
    return [
        {
            "ticker": r.ticker,
            "direction": r.direction,
            "acted": r.acted,
            "reasoning": r.reasoning,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
