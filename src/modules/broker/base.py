"""Abstract broker interface and shared data types.

Order quantity is signed: positive = buy, negative = sell (matching the legacy
convention ``place_market_order(-qty)``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.conf.schema import AssetClass


class BrokerError(Exception):
    pass


class BrokerNotRegisteredError(BrokerError):
    pass


@dataclass(slots=True)
class OrderResult:
    ticker: str
    quantity: float
    status: str  # "filled" | "pending" | "rejected"
    broker_order_id: str | None = None
    avg_price: float | None = None
    paper: bool = False
    reason: str | None = None


@dataclass(slots=True)
class BrokerPosition:
    ticker: str
    quantity: float
    avg_price: float
    market_price: float | None = None


@dataclass(slots=True)
class AccountSummary:
    cash: float
    equity: float
    currency: str = "USD"


class Broker(ABC):
    name: str = "abstract"

    @abstractmethod
    async def place_market_order(
        self, ticker: str, quantity: float, *, asset_class: str = AssetClass.equity.value
    ) -> OrderResult:
        ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        ...

    @abstractmethod
    async def get_account_summary(self) -> AccountSummary:
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        ...

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> OrderResult:
        """Look up the current state of a previously placed order — used to
        reconcile an order that was placed as ``pending`` (or any non-``rejected``/
        ``filled`` status) so a not-yet-confirmed fill never gets recorded as filled
        against local position state (see ExecutionEngine.reconcile_pending_orders)."""
        ...
