"""Price routes: read stored bars and trigger a backfill."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.com import yahoofinance
from src.modules.db.models.user import User
from src.modules.price import storage
from src.modules.price.pipeline import PricePipeline

from ..deps import get_context, get_current_user, get_session

router = APIRouter(prefix="/api/v1/prices", tags=["prices"])


class BackfillIn(BaseModel):
    ticker: str
    days: int = 365


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
