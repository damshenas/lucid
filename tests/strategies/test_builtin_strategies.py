"""M10: built-in strategy behavior (trend_follow, trailing_stop)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.modules.strategy import discover_strategies
from src.modules.strategy.context import PositionView, StrategyContext
from src.modules.signal.sources import ExternalSignal

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
    decision = await strat.run(ctx)
    assert decision.acted
    assert decision.reasoning
    assert decision.event is not None
    assert decision.event.ticker == "AAPL"
    assert decision.event.source == "trend_follow"


async def test_trend_follow_skips_downtrend() -> None:
    strat = _LOADED["trend_follow"]
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        price_data=_df(np.linspace(200.0, 100.0, 260)),
    )
    decision = await strat.run(ctx)
    assert not decision.acted
    assert decision.event is None
    assert "uptrend" in decision.reasoning


async def test_trailing_stop_full_exit_on_stop() -> None:
    strat = _LOADED["trailing_stop"]
    values = np.concatenate([np.full(50, 200.0), np.linspace(200.0, 100.0, 30)])
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        price_data=_df(values),
        position=PositionView(ticker="AAPL", quantity=10, avg_price=200.0),
    )
    decision = await strat.run(ctx)
    assert decision.acted
    assert decision.event is not None
    assert decision.event.quantity_pct is None  # full exit


async def test_trailing_stop_profit_take_partial() -> None:
    strat = _LOADED["trailing_stop"]
    values = np.linspace(100.0, 130.0, 60)
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        price_data=_df(values),
        position=PositionView(ticker="AAPL", quantity=10, avg_price=100.0),
    )
    decision = await strat.run(ctx)
    assert decision.acted
    assert decision.event is not None
    assert decision.event.quantity_pct == 33.0  # tier-1 default partial take
    assert decision.event.profit_tier == 1


async def test_trailing_stop_tier1_skipped_if_already_taken() -> None:
    strat = _LOADED["trailing_stop"]
    values = np.linspace(100.0, 130.0, 60)  # +30%, above tier-1 (20%) not tier-2 (50%)
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        price_data=_df(values),
        position=PositionView(ticker="AAPL", quantity=10, avg_price=100.0, tier1_taken=True),
    )
    decision = await strat.run(ctx)
    assert not decision.acted
    assert decision.event is None


async def test_trailing_stop_tier2_fires_after_tier1() -> None:
    strat = _LOADED["trailing_stop"]
    values = np.linspace(100.0, 160.0, 60)  # +60%, above both tiers
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        price_data=_df(values),
        position=PositionView(ticker="AAPL", quantity=10, avg_price=100.0, tier1_taken=True),
    )
    decision = await strat.run(ctx)
    assert decision.acted
    assert decision.event is not None
    assert decision.event.quantity_pct == 33.0  # tier-2 default partial take
    assert decision.event.profit_tier == 2


async def test_trailing_stop_both_tiers_taken_holds() -> None:
    strat = _LOADED["trailing_stop"]
    values = np.linspace(100.0, 160.0, 60)
    ctx = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        price_data=_df(values),
        position=PositionView(
            ticker="AAPL", quantity=10, avg_price=100.0, tier1_taken=True, tier2_taken=True
        ),
    )
    decision = await strat.run(ctx)
    assert not decision.acted
    assert decision.event is None


async def test_trailing_stop_widens_via_bear_regime() -> None:
    strat = _LOADED["trailing_stop"]
    # A modest dip: with a very tight (bull/neutral) multiplier it breaks the stop;
    # with a very wide bear-regime multiplier the same dip stays well above the
    # (much lower) stop price regardless of the exact ATR value — the two
    # multipliers are set far enough apart (0.5x vs 20x) that this holds for any
    # positive ATR, so the test doesn't depend on computing ATR by hand.
    values = np.concatenate([np.full(60, 200.0), np.linspace(200.0, 190.0, 5)])
    benchmark = _df(np.linspace(200.0, 100.0, 260))  # clear downtrend -> "bear"
    config = {
        "strategy": {
            "trailing_stop": {"atr_multiplier": 0.5, "bear_atr_multiplier": 20.0}
        }
    }

    ctx_bull = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        config=config,
        price_data=_df(values),
        position=PositionView(ticker="AAPL", quantity=10, avg_price=200.0),
    )
    bull_decision = await strat.run(ctx_bull)

    ctx_bear = StrategyContext(
        ticker="AAPL", user_id=1, asset_class="equity",
        config=config,
        price_data=_df(values),
        position=PositionView(ticker="AAPL", quantity=10, avg_price=200.0),
        benchmark_data=benchmark,
    )
    bear_decision = await strat.run(ctx_bear)

    assert bull_decision.acted  # tight 0.5x multiplier: stop breaks
    assert not bear_decision.acted  # wide 20x bear multiplier: stop holds


async def test_signal_follow_buys_without_any_price_data() -> None:
    """The whole point of signal_follow: it must be able to act with
    price_data=None (no locally-stored bars at all) — unlike trend_follow it never
    reads context.price_data. Default min_buy_votes=2, so this needs 2 agreeing
    sources, not just 1."""
    strat = _LOADED["signal_follow"]
    ctx = StrategyContext(
        ticker="NFLX", user_id=1, asset_class="equity",
        price_data=None,
        external_signals=[
            ExternalSignal(source="finviz", ticker="NFLX", direction="buy"),
            ExternalSignal(source="zacks", ticker="NFLX", direction="buy"),
            ExternalSignal(source="barchart", ticker="NFLX", direction="hold"),
        ],
    )
    decision = await strat.run(ctx)
    assert decision.acted
    assert decision.event is not None
    assert decision.event.ticker == "NFLX"
    assert decision.event.source == "signal_follow"
    assert decision.event.confidence == 2 / 3  # 2 of 3 answered sources voted buy


async def test_signal_follow_holds_below_vote_threshold() -> None:
    strat = _LOADED["signal_follow"]
    ctx = StrategyContext(
        ticker="NFLX", user_id=1, asset_class="equity",
        config={"strategy": {"signal_follow": {"min_buy_votes": 2}}},
        external_signals=[
            ExternalSignal(source="finviz", ticker="NFLX", direction="buy"),
            ExternalSignal(source="zacks", ticker="NFLX", direction="sell"),
        ],
    )
    decision = await strat.run(ctx)
    assert not decision.acted
    assert decision.event is None
    assert "need 2" in decision.reasoning


async def test_signal_follow_holds_when_no_source_configured() -> None:
    strat = _LOADED["signal_follow"]
    ctx = StrategyContext(
        ticker="NFLX", user_id=1, asset_class="equity",
        external_signals=[
            ExternalSignal(source="finviz", ticker="NFLX", direction=None, error="not configured"),
        ],
    )
    decision = await strat.run(ctx)
    assert not decision.acted
    assert decision.event is None
    assert decision.reasoning == "no external signal source is configured/reachable for this ticker"
