"""Market regime detection from a benchmark ticker (default SPY).

Strategies call ``detect`` to adjust their own thresholds — it is not enforced by the
execution module.
"""

from __future__ import annotations

import pandas as pd

BULL = "bull"
BEAR = "bear"
NEUTRAL = "neutral"


def detect(benchmark_df: pd.DataFrame, *, fast: int = 50, slow: int = 200, band: float = 0.001) -> str:
    """Return ``bull`` | ``bear`` | ``neutral`` from fast vs slow SMA of close."""
    close = benchmark_df["close"]
    if len(close) < slow:
        return NEUTRAL
    sma_fast = close.rolling(fast).mean().iloc[-1]
    sma_slow = close.rolling(slow).mean().iloc[-1]
    if pd.isna(sma_fast) or pd.isna(sma_slow) or sma_slow == 0:
        return NEUTRAL
    if sma_fast > sma_slow * (1 + band):
        return BULL
    if sma_fast < sma_slow * (1 - band):
        return BEAR
    return NEUTRAL
