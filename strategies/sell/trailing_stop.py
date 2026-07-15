"""Built-in sell strategy: ATR trailing stop with tiered profit taking.

- Full exit when price falls below ``entry - atr * atr_multiplier`` (the multiplier
  widens to ``bear_atr_multiplier`` when the benchmark is in a "bear" regime — see
  ``src.modules.price.regime`` — giving the position more room before the stop cuts
  it, since a broad pullback is more likely to be noise than a bear market).
- Tier 1: once price reaches ``entry * (1 + profit_take_pct_1/100)``, sell
  ``take_pct_1`` percent of the *current* position (fires once per position).
- Tier 2: once price reaches ``entry * (1 + profit_take_pct_2/100)``, sell
  ``take_pct_2`` percent of the *current* position (fires once per position, only
  after tier 1's threshold has also been reached — which it always has, since
  tier 2's threshold is higher).

No additional guardrails beyond the two rules above — deliberately kept simple so it
never blocks a trade for a reason outside these two checks.
"""

from __future__ import annotations

from src.modules.bus import SellSignalEvent
from src.modules.price import regime
from src.modules.price.indicators import compute_snapshot
from src.modules.strategy.context import StrategyContext, StrategyDecision

STRATEGY_NAME = "trailing_stop"
STRATEGY_VERSION = "2.0.0"
STRATEGY_DESCRIPTION = (
    "ATR trailing stop (regime-aware) plus two profit-taking tiers."
)

CONFIG_SCHEMA = {
    "atr_multiplier": {"type": "float", "default": 3.0, "required": False},
    "bear_atr_multiplier": {"type": "float", "default": 4.5, "required": False},
    "profit_take_pct_1": {"type": "float", "default": 20.0, "required": False},
    "take_pct_1": {"type": "float", "default": 33.0, "required": False},
    "profit_take_pct_2": {"type": "float", "default": 50.0, "required": False},
    "take_pct_2": {"type": "float", "default": 33.0, "required": False},
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
    bear_atr_mult = float(
        cfg.get("bear_atr_multiplier", CONFIG_SCHEMA["bear_atr_multiplier"]["default"])
    )
    profit_take_pct_1 = float(
        cfg.get("profit_take_pct_1", CONFIG_SCHEMA["profit_take_pct_1"]["default"])
    )
    take_pct_1 = float(cfg.get("take_pct_1", CONFIG_SCHEMA["take_pct_1"]["default"]))
    profit_take_pct_2 = float(
        cfg.get("profit_take_pct_2", CONFIG_SCHEMA["profit_take_pct_2"]["default"])
    )
    take_pct_2 = float(cfg.get("take_pct_2", CONFIG_SCHEMA["take_pct_2"]["default"]))

    # Regime-aware stop: wider (more tolerant) multiplier in a bear market, since a
    # broad-market pullback dragging this position down with it is less likely to be
    # a genuine reversal than in a bull/neutral regime. Falls back to the baseline
    # multiplier whenever no benchmark data is available yet.
    effective_atr_mult = atr_mult
    if context.benchmark_data is not None and not context.benchmark_data.empty:
        if regime.detect(context.benchmark_data) == regime.BEAR:
            effective_atr_mult = bear_atr_mult

    snap = compute_snapshot(df)
    price = float(df["close"].iloc[-1])
    entry = position.avg_price
    stop_price = entry - snap.atr * effective_atr_mult if snap.atr is not None else None
    tier1_price = entry * (1 + profit_take_pct_1 / 100.0)
    tier2_price = entry * (1 + profit_take_pct_2 / 100.0)

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

    if not position.tier1_taken and price >= tier1_price:
        reasoning = (
            f"price {price:.2f} reached tier-1 profit level ({tier1_price:.2f}), "
            f"selling {take_pct_1}%"
        )
        return StrategyDecision(
            acted=True,
            reasoning=reasoning,
            event=SellSignalEvent(
                ticker=context.ticker,
                user_id=context.user_id,
                source=STRATEGY_NAME,
                asset_class=context.asset_class,
                quantity_pct=take_pct_1,
                reasoning=reasoning,
                profit_tier=1,
            ),
        )

    if not position.tier2_taken and price >= tier2_price:
        reasoning = (
            f"price {price:.2f} reached tier-2 profit level ({tier2_price:.2f}), "
            f"selling {take_pct_2}%"
        )
        return StrategyDecision(
            acted=True,
            reasoning=reasoning,
            event=SellSignalEvent(
                ticker=context.ticker,
                user_id=context.user_id,
                source=STRATEGY_NAME,
                asset_class=context.asset_class,
                quantity_pct=take_pct_2,
                reasoning=reasoning,
                profit_tier=2,
            ),
        )

    if stop_price is None:
        reasoning = f"ATR not available yet; price {price:.2f} vs tier-1 target {tier1_price:.2f}"
    else:
        reasoning = (
            f"holding: price {price:.2f} is above stop ({stop_price:.2f}) and below "
            f"the next profit target"
        )
    return StrategyDecision(acted=False, reasoning=reasoning)
