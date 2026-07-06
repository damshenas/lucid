"""Runtime context handed to a strategy's ``run`` function."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.modules.bus import BuySignalEvent, SellSignalEvent
from src.modules.signal.sources import ExternalSignal


@dataclass(slots=True)
class PositionView:
    ticker: str
    quantity: float
    avg_price: float


@dataclass(slots=True)
class StrategyContext:
    ticker: str
    user_id: int
    asset_class: str
    config: dict[str, Any] = field(default_factory=dict)
    price_data: Any | None = None  # pandas DataFrame of OHLCV
    position: PositionView | None = None
    # Populated only for the sources this strategy declared via its module-level
    # EXTERNAL_SOURCES list (see src/modules/strategy/loader.py) — empty otherwise.
    # See src/modules/signal/sources.py for what counts as a "source" and how a
    # rating is normalized.
    external_signals: list[ExternalSignal] = field(default_factory=list)

    def strategy_config(self, name: str) -> dict[str, Any]:
        """Return the resolved config sub-dict for a named strategy."""
        return (self.config.get("strategy") or {}).get(name, {}) or {}

    def external_signal(self, source: str) -> ExternalSignal | None:
        """Convenience lookup: this ticker's rating from one named source, or
        ``None`` if that source wasn't declared/fetched."""
        return next((s for s in self.external_signals if s.source == source), None)


@dataclass(slots=True)
class StrategyDecision:
    """What a strategy's ``run()`` returns for a single evaluation — always carries a
    human-readable ``reasoning``, whether or not it decided to act, so a full decision
    log (why it bought/sold, and why it didn't) can be shown per strategy (see
    src/modules/db/models/decision.py, TradingRuntime._evaluate_buy/._evaluate_sell,
    and pages/StrategyDetail.tsx)."""

    acted: bool
    reasoning: str
    event: BuySignalEvent | SellSignalEvent | None = None
