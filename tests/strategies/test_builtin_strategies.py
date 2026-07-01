"""M10: built-in strategy behavior (trend_follow, trailing_stop)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.modules.strategy import discover_strategies
from src.modules.strategy.context import PositionView, StrategyContext

_LOADED = {s.name: s for s in discover_strategies("strategies")}


def _df(values: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=len(values), freq="D")
    close = pd.Series(values, index=idx)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": pd.Series(np.full(len(values), 1000.0), index=idx),
        }
    )


async def test_trend_follow_buys_in_uptrend() -> None:
    strat = _LOADED["trend_follow"]
    # A perfectly monotonic synthetic uptrend pins RSI at 100 (every day is a
    # gain, no losses at all), which is unrealistic but also means the default
    # overbought filter would reject it. Raise rsi_max so this test isolates
    # the trend/momentum condition being exercised.
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        config={"strategy": {"trend_follow": {"rsi_max": 101.0}}},
        price_data=_df(np.linspace(100.0, 200.0, 260)),
    )
    signal = await strat.run(ctx)
    assert signal is not None
    assert signal.ticker == "AAPL"
    assert signal.source == "trend_follow"


async def test_trend_follow_skips_downtrend() -> None:
    strat = _LOADED["trend_follow"]
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        price_data=_df(np.linspace(200.0, 100.0, 260)),
    )
    assert await strat.run(ctx) is None


async def test_trailing_stop_full_exit_on_stop() -> None:
    strat = _LOADED["trailing_stop"]
    values = np.concatenate([np.full(50, 200.0), np.linspace(200.0, 100.0, 30)])
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        price_data=_df(values),
        position=PositionView(ticker="AAPL", quantity=10, avg_price=200.0),
    )
    signal = await strat.run(ctx)
    assert signal is not None
    assert signal.quantity_pct is None  # full exit


async def test_trailing_stop_profit_take_partial() -> None:
    strat = _LOADED["trailing_stop"]
    values = np.linspace(100.0, 130.0, 60)
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        price_data=_df(values),
        position=PositionView(ticker="AAPL", quantity=10, avg_price=100.0),
    )
    signal = await strat.run(ctx)
    assert signal is not None
    assert signal.quantity_pct == 50.0  # partial profit take
