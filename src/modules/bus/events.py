"""Domain events published on the bus."""

from __future__ import annotations

from dataclasses import dataclass

from src.conf.schema import AssetClass


@dataclass(slots=True)
class Event:
    """Base class for all events."""


@dataclass(slots=True)
class BuySignalEvent(Event):
    ticker: str
    user_id: int
    source: str
    asset_class: str = AssetClass.equity.value
    confidence: float | None = None
    reasoning: str | None = None


@dataclass(slots=True)
class SellSignalEvent(Event):
    ticker: str
    user_id: int
    source: str
    asset_class: str = AssetClass.equity.value
    confidence: float | None = None
    reasoning: str | None = None
    quantity_pct: float | None = None  # None -> full exit


@dataclass(slots=True)
class OrderFilledEvent(Event):
    user_id: int
    ticker: str
    side: str
    quantity: float
    price: float | None = None
    order_id: int | None = None
    paper: bool = True


@dataclass(slots=True)
class OrderRejectedEvent(Event):
    user_id: int
    ticker: str
    side: str
    reason: str


@dataclass(slots=True)
class PriceFetchedEvent(Event):
    ticker: str
    interval: str
    rows: int
    asset_class: str = AssetClass.equity.value
