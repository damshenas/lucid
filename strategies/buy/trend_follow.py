"""Built-in buy strategy: trend following.

Buys when the medium-term trend is up (SMA50 > SMA200) and RSI is not overbought.
"""

from __future__ import annotations

from src.modules.bus import BuySignalEvent
from src.modules.price.indicators import compute_snapshot
from src.modules.strategy.context import StrategyContext

STRATEGY_NAME = "trend_follow"
STRATEGY_VERSION = "1.0.0"
STRATEGY_DESCRIPTION = "Buy in an uptrend (SMA50 > SMA200) while RSI is below the cap."

CONFIG_SCHEMA = {
    "rsi_max": {"type": "float", "default": 70.0, "required": False},
    "min_momentum": {"type": "float", "default": 0.0, "required": False},
}


async def run(context: StrategyContext) -> BuySignalEvent | None:
    df = context.price_data
    if df is None or len(df) < 200:
        return None

    cfg = context.strategy_config(STRATEGY_NAME)
    rsi_max = float(cfg.get("rsi_max", CONFIG_SCHEMA["rsi_max"]["default"]))
    min_momentum = float(cfg.get("min_momentum", CONFIG_SCHEMA["min_momentum"]["default"]))

    snap = compute_snapshot(df)
    if snap.sma_50 is None or snap.sma_200 is None:
        return None

    uptrend = snap.sma_50 > snap.sma_200
    rsi_ok = snap.rsi is None or snap.rsi < rsi_max
    momentum_ok = snap.momentum is None or snap.momentum >= min_momentum

    if uptrend and rsi_ok and momentum_ok:
        return BuySignalEvent(
            ticker=context.ticker,
            user_id=context.user_id,
            source=STRATEGY_NAME,
            asset_class=context.asset_class,
            confidence=0.6,
            reasoning="SMA50 > SMA200 with RSI in range",
        )
    return None
