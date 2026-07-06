"""Built-in buy strategy: trend following.

Buys when the medium-term trend is up (SMA50 > SMA200) and RSI is not overbought.
"""

from __future__ import annotations

from src.modules.bus import BuySignalEvent
from src.modules.price.indicators import compute_snapshot
from src.modules.strategy.context import StrategyContext, StrategyDecision

STRATEGY_NAME = "trend_follow"
STRATEGY_VERSION = "1.0.0"
STRATEGY_DESCRIPTION = "Buy in an uptrend (SMA50 > SMA200) while RSI is below the cap."
# Tells the UI's per-strategy page to show the signals feed (filtered to this
# strategy's own signals) — see src/modules/strategy/loader.py and
# pages/StrategyDetail.tsx. No other built-in strategy uses this yet.
FEATURES = ["signals"]

CONFIG_SCHEMA = {
    "rsi_max": {"type": "float", "default": 70.0, "required": False},
    "min_momentum": {"type": "float", "default": 0.0, "required": False},
}


async def run(context: StrategyContext) -> StrategyDecision:
    df = context.price_data
    if df is None or len(df) < 200:
        have = 0 if df is None else len(df)
        return StrategyDecision(
            acted=False, reasoning=f"only {have} bars stored, need at least 200"
        )

    cfg = context.strategy_config(STRATEGY_NAME)
    rsi_max = float(cfg.get("rsi_max", CONFIG_SCHEMA["rsi_max"]["default"]))
    min_momentum = float(cfg.get("min_momentum", CONFIG_SCHEMA["min_momentum"]["default"]))

    snap = compute_snapshot(df)
    if snap.sma_50 is None or snap.sma_200 is None:
        return StrategyDecision(acted=False, reasoning="SMA50/SMA200 not available yet")

    uptrend = snap.sma_50 > snap.sma_200
    rsi_ok = snap.rsi is None or snap.rsi < rsi_max
    momentum_ok = snap.momentum is None or snap.momentum >= min_momentum

    if uptrend and rsi_ok and momentum_ok:
        reasoning = (
            f"SMA50 ({snap.sma_50:.2f}) > SMA200 ({snap.sma_200:.2f}) with RSI "
            f"({snap.rsi:.1f} < {rsi_max}) and momentum in range"
            if snap.rsi is not None
            else f"SMA50 ({snap.sma_50:.2f}) > SMA200 ({snap.sma_200:.2f}) with momentum in range"
        )
        return StrategyDecision(
            acted=True,
            reasoning=reasoning,
            event=BuySignalEvent(
                ticker=context.ticker,
                user_id=context.user_id,
                source=STRATEGY_NAME,
                asset_class=context.asset_class,
                confidence=0.6,
                reasoning=reasoning,
            ),
        )

    if not uptrend:
        reasoning = f"no uptrend: SMA50 ({snap.sma_50:.2f}) <= SMA200 ({snap.sma_200:.2f})"
    elif not rsi_ok:
        reasoning = f"RSI too high: {snap.rsi:.1f} >= cap {rsi_max}"
    else:
        reasoning = f"momentum too low: {snap.momentum:.4f} < required {min_momentum}"
    return StrategyDecision(acted=False, reasoning=reasoning)
