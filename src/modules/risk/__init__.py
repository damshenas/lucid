"""Pre-trade risk gate. Disabled by default.

The gate exists as a shell so it can be toggled per-user via DB config
(``risk.enabled = true``) without code changes. When disabled, every check approves.
Selling always approves — exits reduce exposure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.conf.schema import RiskConfig


@dataclass(slots=True)
class RiskContext:
    order_usd: float
    open_positions: int
    portfolio_value: float
    daily_buy_usd: float = 0.0


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    reason: str | None = None


class RiskGate:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        defaults = RiskConfig().model_dump()
        self._c = {**defaults, **(config or {})}

    @property
    def enabled(self) -> bool:
        return bool(self._c.get("enabled", False))

    def evaluate_buy(self, ctx: RiskContext) -> RiskDecision:
        if not self.enabled:
            return RiskDecision(True)

        if ctx.order_usd > self._c["max_single_trade_usd"]:
            return RiskDecision(False, "max_single_trade_usd")
        if ctx.daily_buy_usd + ctx.order_usd > self._c["max_daily_buy_usd"]:
            return RiskDecision(False, "max_daily_buy_usd")
        if ctx.open_positions >= self._c["max_open_positions"]:
            return RiskDecision(False, "max_open_positions")
        if ctx.portfolio_value > 0:
            position_pct = ctx.order_usd / ctx.portfolio_value * 100.0
            if position_pct > self._c["max_position_pct"]:
                return RiskDecision(False, "max_position_pct")
        return RiskDecision(True)

    def evaluate_sell(self, ctx: RiskContext) -> RiskDecision:
        # Exits reduce exposure and are always allowed.
        return RiskDecision(True)


__all__ = ["RiskContext", "RiskDecision", "RiskGate"]
