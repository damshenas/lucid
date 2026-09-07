"""Backtrader integration: historical backtesting and a live bridge onto the event bus.

- ``run_backtest`` runs a ``bt.Strategy`` against a historical OHLCV frame and returns
  performance metrics.
- ``BacktraderLiveBridge`` runs a strategy and translates its broker orders into
  ``BuySignalEvent`` / ``SellSignalEvent`` published to the bus.

``backtrader`` is imported lazily so importing this module stays cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.modules.bus import BuySignalEvent, EventBus, SellSignalEvent
from src.conf.schema import AssetClass


@dataclass(slots=True)
class BacktestResult:
    initial_cash: float
    final_value: float
    return_pct: float
    sharpe: float | None = None
    max_drawdown: float | None = None
    total_trades: int = 0


def _make_feed(df: pd.DataFrame):
    import backtrader as bt

    return bt.feeds.PandasData(
        dataname=df,
        datetime=None,
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        openinterest=None,
    )


def run_backtest(
    strategy_class: type,
    df: pd.DataFrame,
    *,
    initial_cash: float = 100_000.0,
    commission: float = 0.0,
    strategy_kwargs: dict[str, Any] | None = None,
) -> BacktestResult:
    import backtrader as bt

    cerebro = bt.Cerebro()
    cerebro.adddata(_make_feed(df))
    cerebro.addstrategy(strategy_class, **(strategy_kwargs or {}))
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    strat = cerebro.run()[0]
    final_value = float(cerebro.broker.getvalue())

    try:
        max_dd = float(strat.analyzers.dd.get_analysis()["max"]["drawdown"])
    except (KeyError, TypeError):
        max_dd = None
    try:
        sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio")
        sharpe = None if sharpe is None else float(sharpe)
    except (AttributeError, TypeError):
        sharpe = None
    try:
        total_trades = int(strat.analyzers.trades.get_analysis().get("total", {}).get("total", 0))
    except (AttributeError, TypeError):
        total_trades = 0

    return BacktestResult(
        initial_cash=initial_cash,
        final_value=final_value,
        return_pct=(final_value - initial_cash) / initial_cash * 100.0,
        sharpe=sharpe,
        max_drawdown=max_dd,
        total_trades=total_trades,
    )


@dataclass
class BacktraderLiveBridge:
    """Runs a strategy and emits Buy/Sell signal events for its orders.

    Sell events carry ``quantity_pct`` computed from the completed order's actual
    size relative to the position size just before it, so a Backtrader strategy's
    partial sell is translated as a partial sell in Lucid too (bugs.md finding 22)
    instead of always requesting a full exit (``SellSignalEvent.quantity_pct=None``
    means "sell everything", the previous behavior for every sell regardless of
    Backtrader's real order size).

    Buy events carry no size at all — this is not a bridge-specific gap, no
    ``BuySignalEvent`` in Lucid does (every buy strategy's suggested size, if any,
    is discarded; ``ExecutionEngine.handle_buy`` always computes the real order
    quantity from ``execution.quantity_mode`` — fixed_usd/pct_portfolio/half_kelly).
    A Backtrader strategy's chosen buy size is therefore informational only and has
    no effect on the resulting live order size, exactly like every other strategy.
    """

    bus: EventBus
    user_id: int
    asset_class: str = AssetClass.equity.value
    source: str = "backtrader"
    published: list[Any] = field(default_factory=list)

    async def run_live(
        self,
        strategy_class: type,
        df: pd.DataFrame,
        ticker: str,
        *,
        initial_cash: float = 100_000.0,
        commission: float = 0.0,
    ) -> list[Any]:
        import backtrader as bt

        # (is_buy, order size (signed; negative for a sell), fill price, position
        # size immediately AFTER this order completed) — the position size lets the
        # sell translation below recover "how much was held right before this sell"
        # (post_size + sell_size) without needing its own separate position tracker.
        recorded: list[tuple[bool, float, float, float]] = []

        class _OrderRecorder(bt.Analyzer):
            def notify_order(self, order: Any) -> None:
                if order.status == order.Completed:
                    recorded.append(
                        (
                            order.isbuy(),
                            float(order.size),
                            float(order.executed.price),
                            float(self.strategy.position.size),
                        )
                    )

        cerebro = bt.Cerebro()
        cerebro.adddata(_make_feed(df))
        cerebro.addstrategy(strategy_class)
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=commission)
        cerebro.addanalyzer(_OrderRecorder, _name="orders")
        cerebro.run()

        for is_buy, size, _price, post_size in recorded:
            if is_buy:
                event: Any = BuySignalEvent(
                    ticker=ticker,
                    user_id=self.user_id,
                    source=self.source,
                    asset_class=self.asset_class,
                )
            else:
                sell_size = abs(size)
                pre_size = post_size + sell_size
                if abs(post_size) < 1e-9 or pre_size <= 0:
                    quantity_pct = None  # fully closed the position
                else:
                    quantity_pct = min(100.0, (sell_size / pre_size) * 100.0)
                event = SellSignalEvent(
                    ticker=ticker,
                    user_id=self.user_id,
                    source=self.source,
                    asset_class=self.asset_class,
                    quantity_pct=quantity_pct,
                )
            self.published.append(event)
            await self.bus.publish(event)
        return self.published


__all__ = ["BacktestResult", "BacktraderLiveBridge", "run_backtest"]
