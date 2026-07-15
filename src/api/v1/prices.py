"""Price routes: read stored bars, trigger a backfill, and manage the watchlist."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authorization import Permission
from src.modules.com import yahoofinance
from src.modules.db.models.user import User
from src.modules.db.repositories.price import PriceWatchlistRepository
from src.modules.price import storage
from src.modules.price.pipeline import PricePipeline

from ..deps import get_context, get_current_user, get_session, require_permission

router = APIRouter(prefix="/api/v1/prices", tags=["prices"])

PollInterval = Literal["1m", "1h"]
Region = Literal["us", "eu", "em"]


class BackfillIn(BaseModel):
    ticker: str
    days: int = 365


class WatchlistIn(BaseModel):
    ticker: str
    asset_class: str = "equity"
    poll_interval: PollInterval = "1h"
    region: Region = "us"


class WatchlistPatch(BaseModel):
    enabled: bool | None = None
    poll_interval: PollInterval | None = None
    region: Region | None = None


# Registered before the "/{ticker}" catch-all below so "/watchlist" doesn't get
# swallowed by it (FastAPI/Starlette matches routes in registration order).
@router.get("/watchlist")
async def list_watchlist(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    storage_path = get_context(request).settings.price.storage_path
    rows = await PriceWatchlistRepository(session).list_all()
    result = [
        {
            "ticker": row.ticker,
            "asset_class": row.asset_class,
            "enabled": row.enabled,
            "poll_interval": row.poll_interval,
            "region": row.region,
            "has_bars": storage.read_bars(storage_path, row.ticker, "1d") is not None,
            "on_watchlist": True,
        }
        for row in rows
    ]
    # Also surface any ticker with stored bars from before it was (or without ever
    # being) added to the watchlist — e.g. an ad-hoc backfill from the Prices page —
    # so the ticker autocomplete (see pages/Prices.tsx) covers every known ticker,
    # not only ones already on the watchlist. Marked on_watchlist=False so a client
    # never mistakes one of these for a real, already-saved watchlist row (a POST is
    # still required to actually add it — a PATCH/DELETE for a ticker like this 404s,
    # same as for any other unknown ticker).
    known = {r["ticker"] for r in result}
    for ticker in storage.list_tickers(storage_path, "1d"):
        if ticker not in known:
            result.append(
                {
                    "ticker": ticker,
                    "asset_class": "equity",
                    "enabled": False,
                    "poll_interval": "1h",
                    "region": "us",
                    "has_bars": True,
                    "on_watchlist": False,
                }
            )
    return sorted(result, key=lambda r: r["ticker"])


@router.post("/watchlist", status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    body: WatchlistIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.edit_own_strategies)),
) -> dict[str, Any]:
    row = await PriceWatchlistRepository(session).upsert(
        body.ticker, asset_class=body.asset_class, poll_interval=body.poll_interval, region=body.region
    )
    await session.commit()
    return {
        "ticker": row.ticker,
        "asset_class": row.asset_class,
        "enabled": row.enabled,
        "poll_interval": row.poll_interval,
        "region": row.region,
    }


@router.patch("/watchlist/{ticker}")
async def update_watchlist_item(
    ticker: str,
    body: WatchlistPatch,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.edit_own_strategies)),
) -> dict[str, Any]:
    repo = PriceWatchlistRepository(session)
    row = None
    if body.enabled is not None:
        row = await repo.set_enabled(ticker, body.enabled)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{ticker}' is not on the watchlist")
    if body.poll_interval is not None:
        row = await repo.set_poll_interval(ticker, body.poll_interval)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{ticker}' is not on the watchlist")
    if body.region is not None:
        row = await repo.set_region(ticker, body.region)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{ticker}' is not on the watchlist")
    if row is None:
        row = await repo.get_by_ticker(ticker.upper())
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{ticker}' is not on the watchlist")
    await session.commit()
    return {
        "ticker": row.ticker,
        "asset_class": row.asset_class,
        "enabled": row.enabled,
        "poll_interval": row.poll_interval,
        "region": row.region,
    }


@router.delete("/watchlist/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    ticker: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.edit_own_strategies)),
) -> None:
    removed = await PriceWatchlistRepository(session).delete_by_ticker(ticker)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{ticker}' is not on the watchlist")
    await session.commit()


@router.get("/{ticker}")
async def get_prices(
    request: Request,
    ticker: str,
    interval: str = Query(default="1d"),
    limit: int = Query(default=250, le=2000),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    storage_path = get_context(request).settings.price.storage_path
    df = storage.read_bars(storage_path, ticker, interval)
    if df is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no bars for {ticker} [{interval}]")
    tail = df.tail(limit)
    bars = [
        {"date": str(idx), **{k: float(v) for k, v in row.items()}}
        for idx, row in tail.iterrows()
    ]
    return {"ticker": ticker.upper(), "interval": interval, "bars": bars}


@router.post("/backfill")
async def backfill(
    request: Request,
    body: BackfillIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    storage_path = get_context(request).settings.price.storage_path
    pipeline = PricePipeline(
        storage_path=storage_path,
        fetcher=yahoofinance.fetch_ohlcv,
        watchlist_provider=lambda: [],
    )
    rows = await pipeline.run_backfill(body.ticker, days=body.days)
    return {"rows": rows}
