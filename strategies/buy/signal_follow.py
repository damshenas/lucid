"""Built-in buy strategy: follow third-party signal providers.

Unlike ``trend_follow`` (SMA50/SMA200/RSI computed from Lucid's own locally-stored
daily bars, which needs 200+ days of history before it can say anything), this
strategy makes its buy/no-buy decision entirely from external signal providers'
current ratings (Finviz/TradingView/Zacks/Barchart — see
``src/modules/signal/sources.py``) and never looks at ``context.price_data`` at all.
It still only ever runs against the shared price watchlist (see
``TradingRuntime.run_strategies`` in ``src/api/runtime.py``) — that's the candidate
list a buy strategy needs regardless of what it bases its decision on — but it has no
"needs N days of bars first" warm-up period the way a local-indicator strategy does.
"""

from __future__ import annotations

from src.modules.bus import BuySignalEvent
from src.modules.strategy.context import StrategyContext, StrategyDecision

STRATEGY_NAME = "signal_follow"
STRATEGY_VERSION = "1.0.0"
STRATEGY_DESCRIPTION = (
    "Buy when external signal providers (Finviz/TradingView/Zacks/Barchart) rate a "
    "ticker 'buy' — no local price history required."
)
FEATURES = ["signals"]
# Every currently-supported provider (src/modules/signal/sources.py SOURCE_NAMES) —
# a source only actually participates once its credentials are configured
# (GET /api/v1/signals/sources shows what's usable right now); an unconfigured one
# just comes back with error="not configured" and doesn't count toward the vote.
EXTERNAL_SOURCES = ["finviz", "tradingview", "zacks", "barchart"]

CONFIG_SCHEMA = {
    "min_buy_votes": {"type": "int", "default": 1, "required": False},
}


async def run(context: StrategyContext) -> StrategyDecision:
    cfg = context.strategy_config(STRATEGY_NAME)
    min_votes = int(cfg.get("min_buy_votes", CONFIG_SCHEMA["min_buy_votes"]["default"]))

    # error is None -> the source was configured and actually answered (even if its
    # own opinion is "hold"/unparseable, i.e. direction is None); treat "not
    # configured"/"request failed" the same way (out of the vote entirely), never as
    # a "no" vote.
    answered = [s for s in context.external_signals if s.error is None]
    if not answered:
        return StrategyDecision(
            acted=False,
            reasoning="no external signal source is configured/reachable for this ticker",
        )

    buy_votes = [s for s in answered if s.direction == "buy"]
    if len(buy_votes) >= min_votes:
        reasoning = (
            f"{len(buy_votes)}/{len(answered)} source(s) rate buy "
            f"(need {min_votes}): {', '.join(s.source for s in buy_votes)}"
        )
        return StrategyDecision(
            acted=True,
            reasoning=reasoning,
            event=BuySignalEvent(
                ticker=context.ticker,
                user_id=context.user_id,
                source=STRATEGY_NAME,
                asset_class=context.asset_class,
                confidence=len(buy_votes) / len(answered),
                reasoning=reasoning,
            ),
        )

    votes = ", ".join(f"{s.source}={s.direction or 'no opinion'}" for s in answered)
    reasoning = f"only {len(buy_votes)}/{len(answered)} source(s) rate buy (need {min_votes}): {votes}"
    return StrategyDecision(acted=False, reasoning=reasoning)
