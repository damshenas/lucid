"""Runtime context handed to a strategy's ``run`` function."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.modules.bus import BuySignalEvent, SellSignalEvent


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

    def strategy_config(self, name: str) -> dict[str, Any]:
        """Return the resolved config sub-dict for a named strategy."""
        return (self.config.get("strategy") or {}).get(name, {}) or {}


@dataclass(slots=True)
class StrategyDecision:
    """What a strategy's ``run()`` returns for a single evaluation — always carries a
    human-readable ``reasoning``, whether or not it decided to act, so a full decision
    log (why it bought/sold, and why it didn't) can be shown per strategy (see
    src/modules/db/models/decision.py, TradingRuntime._evaluate_ticker, and
    pages/StrategyDetail.tsx)."""

    acted: bool
    reasoning: str
    event: BuySignalEvent | SellSignalEvent | None = None
