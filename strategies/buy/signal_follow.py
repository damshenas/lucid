"""Built-in buy strategy: follow third-party signal providers.

Unlike ``trend_follow`` (SMA50/SMA200/RSI computed from Lucid's own locally-stored
daily bars, which needs 200+ days of history before it can say anything), this
strategy makes its buy/no-buy decision entirely from external signal providers'
current ratings (Finviz/TradingView — see ``src/modules/signal/sources.py``) and
never looks at ``context.price_data`` at all. Both wired sources hit real, fixed
public endpoints and need no credentials at all (Zacks/Barchart exist only as
explicit ``DISABLED`` placeholders — see ``src.modules.com.zacks``/``.barchart`` —
since their real data needs a headless-browser anti-bot bypass this repo doesn't
run; they are deliberately not in ``EXTERNAL_SOURCES`` below).

It also does NOT use the shared price watchlist as its candidate list — unlike every
other buy strategy, it sets ``USES_WATCHLIST = False`` so ``TradingRuntime.
run_strategies`` (src/api/runtime.py) discovers candidate tickers directly from this
strategy's own ``EXTERNAL_SOURCES`` (via ``SignalSourceRegistry.discover()``) instead
of iterating any predefined list. The default ``min_buy_votes = 2`` means a ticker
only gets acted on once both wired sources currently agree it's a buy — a single
source's opinion alone is treated as inconclusive, not a signal to act on.
"""

from __future__ import annotations

from src.modules.bus import BuySignalEvent
from src.modules.strategy.context import StrategyContext, StrategyDecision

STRATEGY_NAME = "signal_follow"
STRATEGY_VERSION = "2.1.0"
STRATEGY_DESCRIPTION = (
    "Buy when at least 2 external signal providers (Finviz/TradingView) currently "
    "rate a ticker 'buy' — no local price history, no watchlist entry, and no "
    "credentials required; candidates are discovered directly from the providers "
    "themselves."
)
FEATURES = ["signals"]
# Every currently-wired provider (src/modules/signal/sources.py SOURCE_NAMES) — both
# hit real public endpoints with no credentials needed at all (see their connector
# docstrings). Zacks/Barchart are intentionally excluded (DISABLED placeholders).
EXTERNAL_SOURCES = ["finviz", "tradingview"]
# Candidate tickers come from EXTERNAL_SOURCES' own discovery endpoints (see
# SignalSourceRegistry.discover), never from the shared price watchlist.
USES_WATCHLIST = False

CONFIG_SCHEMA = {
    "min_buy_votes": {"type": "int", "default": 2, "required": False},
}


async def run(context: StrategyContext) -> StrategyDecision:
    cfg = context.strategy_config(STRATEGY_NAME)
    min_votes = int(cfg.get("min_buy_votes", CONFIG_SCHEMA["min_buy_votes"]["default"]))

    # error is None -> the source was configured and actually answered (even if its
    # own opinion is "hold"/unparseable, i.e. direction is None); treat "not
    # configured"/"request failed" the same way (out of the vote entirely), never as
    # a "no" vote. Deduped by source name (first occurrence wins) so two rows from
    # the same provider (e.g. two exchange listings normalizing to this ticker) can
    # never count as two independent votes — "2 providers agree" must mean two
    # distinct providers, not two rows (bugs.md finding 14).
    seen_sources: dict[str, object] = {}
    for sig in context.external_signals:
        if sig.error is None:
            seen_sources.setdefault(sig.source, sig)
    answered = list(seen_sources.values())
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
