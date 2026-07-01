"""In-memory paper-trading broker.

Simulates fills without any network. Prices come from an injected provider (the price
module wires this in later) or an internal price table set via ``set_price``.
"""

from __future__ import annotations

from collections.abc import Callable

from src.conf.schema import AssetClass

from .base import AccountSummary, Broker, BrokerPosition, OrderResult

PriceProvider = Callable[[str], float]


class PaperBroker(Broker):
    name = "paper"

    def __init__(
        self,
        *,
        starting_cash: float = 100_000.0,
        price_provider: PriceProvider | None = None,
    ) -> None:
        self._cash = starting_cash
        self._price_provider = price_provider
        self._prices: dict[str, float] = {}
        self._positions: dict[str, BrokerPosition] = {}
        self._order_seq = 0

    def set_price(self, ticker: str, price: float) -> None:
        self._prices[ticker] = price

    def _price(self, ticker: str) -> float:
        if self._price_provider is not None:
            return self._price_provider(ticker)
        return self._prices.get(ticker, 100.0)

    async def place_market_order(
        self, ticker: str, quantity: float, *, asset_class: str = AssetClass.equity.value
    ) -> OrderResult:
        if quantity == 0:
            return OrderResult(ticker, 0.0, "rejected", paper=True, reason="zero quantity")

        price = self._price(ticker)
        self._order_seq += 1
        order_id = f"paper-{self._order_seq}"
        existing = self._positions.get(ticker)

        if quantity > 0:  # buy
            self._cash -= quantity * price
            if existing is None:
                self._positions[ticker] = BrokerPosition(ticker, quantity, price, price)
            else:
                total_qty = existing.quantity + quantity
                existing.avg_price = (
                    (existing.avg_price * existing.quantity) + (price * quantity)
                ) / total_qty
                existing.quantity = total_qty
        else:  # sell
            sell_qty = min(-quantity, existing.quantity) if existing else 0.0
            if sell_qty <= 0:
                return OrderResult(
                    ticker, quantity, "rejected", paper=True, reason="no position to sell"
                )
            self._cash += sell_qty * price
            existing.quantity -= sell_qty
            if existing.quantity <= 1e-9:
                self._positions.pop(ticker, None)

        return OrderResult(
            ticker=ticker,
            quantity=quantity,
            status="filled",
            broker_order_id=order_id,
            avg_price=price,
            paper=True,
        )

    async def get_positions(self) -> list[BrokerPosition]:
        for pos in self._positions.values():
            pos.market_price = self._price(pos.ticker)
        return list(self._positions.values())

    async def get_account_summary(self) -> AccountSummary:
        holdings = sum(p.quantity * self._price(p.ticker) for p in self._positions.values())
        return AccountSummary(cash=self._cash, equity=self._cash + holdings)

    async def cancel_order(self, broker_order_id: str) -> bool:
        # Paper orders fill immediately; nothing to cancel.
        return False
