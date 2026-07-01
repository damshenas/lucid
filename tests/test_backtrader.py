"""M11: backtesting metrics and the live bridge to the bus.

Skipped automatically where ``backtrader`` is not installed (it is present in the
Docker build where the suite gates the image).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

bt = pytest.importorskip("backtrader")

from src.modules.backtrader import BacktraderLiveBridge, run_backtest  # noqa: E402
from src.modules.bus import BuySignalEvent, EventBus, SellSignalEvent  # noqa: E402


def _df(n: int = 40) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100.0, 140.0, n), index=idx)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": pd.Series(np.full(n, 1000.0), index=idx),
        }
    )


class _BuyAndHold(bt.Strategy):
    def next(self) -> None:
        if not self.position and len(self) == 2:
            self.buy(size=10)


class _BuyThenSell(bt.Strategy):
    def next(self) -> None:
        if len(self) == 2 and not self.position:
            self.buy(size=10)
        elif len(self) == 20 and self.position:
            self.sell(size=10)


def test_run_backtest_returns_metrics() -> None:
    result = run_backtest(_BuyAndHold, _df(), initial_cash=100_000.0)
    assert result.initial_cash == 100_000.0
    assert result.final_value > 0
    assert isinstance(result.return_pct, float)


async def test_live_bridge_emits_events() -> None:
    bus = EventBus()
    seen: list[object] = []
    bus.subscribe(BuySignalEvent, lambda e: seen.append(e))
    bus.subscribe(SellSignalEvent, lambda e: seen.append(e))

    bridge = BacktraderLiveBridge(bus=bus, user_id=1)
    published = await bridge.run_live(_BuyThenSell, _df(), "AAPL")

    assert any(isinstance(e, BuySignalEvent) for e in published)
    assert len(seen) == len(published)
