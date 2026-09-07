"""Signal read routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.db.models.user import User
from src.modules.db.repositories.signal import SignalRepository
from src.modules.signal.sources import SOURCE_NAMES, SignalSourceRegistry

from ..deps import get_context, get_current_user, get_session

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


class SignalCheckIn(BaseModel):
    ticker: str
    sources: list[str] | None = None


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


# Registered before any "/{...}" catch-all would be added below, matching the same
# ordering rule as prices.py's "/watchlist" route.
@router.get("/sources")
async def list_signal_sources(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Which external signal sources (src/modules/signal/sources.py) are usable right
    now for this user — i.e. by a strategy declaring ``EXTERNAL_SOURCES`` or by
    ``POST /sources/check`` below. A source that needs no credentials at all (every
    one currently wired — finviz/tradingview hit fixed public endpoints) is always
    "configured"; one that does is checked via ``SignalSourceRegistry.is_configured``,
    which resolves whichever credential(s) that specific source actually declares
    (some need only an API key, e.g. finnhub/fmp — not a base_url)."""
    registry = SignalSourceRegistry(get_context(request).credential_manager(session), user_id=user.id)
    return [{"source": name, "configured": await registry.is_configured(name)} for name in SOURCE_NAMES]


@router.post("/sources/check")
async def check_signal_sources(
    request: Request,
    body: SignalCheckIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """On-demand test of one or more external signal sources for a ticker — the same
    machinery a strategy declaring ``EXTERNAL_SOURCES`` uses at runtime (see
    ``TradingRuntime._external_signals`` in src/api/runtime.py), exposed here so a
    source/credential can be verified without waiting for a strategy to run."""
    registry = SignalSourceRegistry(get_context(request).credential_manager(session), user_id=user.id)
    results = await registry.fetch(body.ticker.upper(), body.sources)
    return [
        {"source": r.source, "ticker": r.ticker, "direction": r.direction, "error": r.error}
        for r in results
    ]
