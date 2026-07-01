"""Runtime context handed to a strategy's ``run`` function."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
