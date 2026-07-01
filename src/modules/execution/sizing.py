"""Order sizing for the execution pipeline."""

from __future__ import annotations

from typing import Any

from src.conf.schema import QuantityMode


def _normalize_confidence(confidence: float | None) -> float | None:
    if confidence is None:
        return None
    value = confidence / 100.0 if confidence > 1.0 else confidence
    return max(0.0, min(1.0, value))


def compute_buy_quantity(
    *,
    mode: str,
    price: float,
    config: dict[str, Any],
    portfolio_value: float,
    confidence: float | None = None,
) -> float:
    """Return the number of shares to buy for the given sizing mode.

    Modes: ``fixed_usd``, ``pct_portfolio``, ``half_kelly``.
    """
    if price <= 0:
        return 0.0

    fixed_usd = float(config.get("fixed_usd", 100.0))
    pct = float(config.get("pct_portfolio", 5.0)) / 100.0

    if mode == QuantityMode.fixed_usd.value:
        usd = fixed_usd
    elif mode == QuantityMode.pct_portfolio.value:
        usd = portfolio_value * pct
    elif mode == QuantityMode.half_kelly.value:
        p = _normalize_confidence(confidence)
        if p is None:
            usd = portfolio_value * pct
        else:
            # Even-money payoff assumption: kelly = 2p - 1; half-kelly halves it.
            half_kelly = max(0.0, (2.0 * p - 1.0) / 2.0)
            usd = portfolio_value * half_kelly
    else:
        usd = fixed_usd

    return max(0.0, usd / price)
