"""Signal read routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.db.models.user import User
from src.modules.db.repositories.signal import SignalRepository

from ..deps import get_current_user, get_session

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


@router.get("")
async def list_signals(
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    source: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    signals = await SignalRepository(session).list_by_user(
        user.id, limit=limit, offset=offset, source=source
    )
    return [
        {
            "ticker": s.ticker,
            "direction": s.direction,
            "confidence": s.confidence,
            "source": s.source,
            "status": s.status,
        }
        for s in signals
    ]
