"""Built-in sell strategy: ATR trailing stop with profit taking.

- Full exit when price falls below ``entry - atr * atr_multiplier``.
- Partial exit (``take_pct``) once price reaches ``entry * (1 + profit_take_pct/100)``.
"""

from __future__ import annotations

from src.modules.bus import SellSignalEvent
from src.modules.price.indicators import compute_snapshot
from src.modules.strategy.context import StrategyContext, StrategyDecision

STRATEGY_NAME = "trailing_stop"
STRATEGY_VERSION = "1.0.0"
STRATEGY_DESCRIPTION = "ATR trailing stop plus profit taking at a configurable level."

CONFIG_SCHEMA = {
    "atr_multiplier": {"type": "float", "default": 3.0, "required": False},
    "profit_take_pct": {"type": "float", "default": 20.0, "required": False},
    "take_pct": {"type": "float", "default": 50.0, "required": False},
}


async def run(context: StrategyContext) -> StrategyDecision:
    position = context.position
    df = context.price_data
    if position is None:
        return StrategyDecision(acted=False, reasoning="no open position to manage")
    if df is None or df.empty:
        return StrategyDecision(acted=False, reasoning="no stored price bars yet")

    cfg = context.strategy_config(STRATEGY_NAME)
    atr_mult = float(cfg.get("atr_multiplier", CONFIG_SCHEMA["atr_multiplier"]["default"]))
    profit_take_pct = float(cfg.get("profit_take_pct", CONFIG_SCHEMA["profit_take_pct"]["default"]))
    take_pct = float(cfg.get("take_pct", CONFIG_SCHEMA["take_pct"]["default"]))

    snap = compute_snapshot(df)
    price = float(df["close"].iloc[-1])
    entry = position.avg_price
    stop_price = entry - snap.atr * atr_mult if snap.atr is not None else None
    take_price = entry * (1 + profit_take_pct / 100.0)

    if stop_price is not None and price < stop_price:
        reasoning = f"price {price:.2f} broke ATR trailing stop ({stop_price:.2f})"
        return StrategyDecision(
            acted=True,
            reasoning=reasoning,
            event=SellSignalEvent(
                ticker=context.ticker,
                user_id=context.user_id,
                source=STRATEGY_NAME,
                asset_class=context.asset_class,
                reasoning=reasoning,
            ),
        )

    if price >= take_price:
        reasoning = f"price {price:.2f} reached profit-taking level ({take_price:.2f}), selling {take_pct}%"
        return StrategyDecision(
            acted=True,
            reasoning=reasoning,
            event=SellSignalEvent(
                ticker=context.ticker,
                user_id=context.user_id,
                source=STRATEGY_NAME,
                asset_class=context.asset_class,
                quantity_pct=take_pct,
                reasoning=reasoning,
            ),
        )

    if stop_price is None:
        reasoning = f"ATR not available yet; price {price:.2f} vs profit target {take_price:.2f}"
    else:
        reasoning = (
            f"holding: price {price:.2f} is above stop ({stop_price:.2f}) "
            f"and below profit target ({take_price:.2f})"
        )
    return StrategyDecision(acted=False, reasoning=reasoning)
