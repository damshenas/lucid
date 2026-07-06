"""Backtesting route.

Lightweight evaluation: replays the user's active buy strategy across stored bars and
reports how many buy signals it would have produced. Full ``bt.Strategy`` backtesting is
available programmatically via ``modules/backtrader.run_backtest``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.db.models.user import User
from src.modules.price import storage
from src.modules.strategy.context import StrategyContext

from ..deps import get_context, get_current_user, get_session

router = APIRouter(prefix="/api/v1/backtesting", tags=["backtesting"])

_MIN_BARS = 200
_STEP = 5


class BacktestIn(BaseModel):
    ticker: str
    interval: str = "1d"
    strategy: str | None = None


@router.post("/run")
async def run(
    request: Request,
    body: BacktestIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ctx = get_context(request)
    storage_path = ctx.settings.price.storage_path
    df = storage.read_bars(storage_path, body.ticker, body.interval)
    if df is None or len(df) < _MIN_BARS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not enough stored bars to backtest")

    config = ctx.config_service(session)
    values = await config.compile_values(user_id=user.id)
    service = ctx.strategy_service(session)
    strategy = (
        service.get_loaded(body.strategy)
        if body.strategy
        else service.get_active(values, "buy")
    )
    if strategy is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no active buy strategy")

    signals = 0
    for i in range(_MIN_BARS, len(df), _STEP):
        window = df.iloc[:i]
        decision = await strategy.run(
            StrategyContext(
                ticker=body.ticker,
                user_id=user.id,
                asset_class="equity",
                config=values,
                price_data=window,
            )
        )
        if decision.acted:
            signals += 1

    return {"ticker": body.ticker.upper(), "strategy": strategy.name, "buy_signals": signals}
