"""Strategy routes: list, scan, and per-user activation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authorization import Permission
from src.modules.db.models.user import User

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
        f"strategy.active_{direction}_strategy", name, user_id=user.id
    )
    await session.commit()
    return {"active": name, "direction": direction}
