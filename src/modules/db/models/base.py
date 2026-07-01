"""Declarative base, shared mixins, and domain enums for ORM models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Re-exported so callers can import a single canonical AssetClass.
from src.conf.schema import AssetClass  # noqa: F401


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class TimestampMixin:
    """Adds created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Role(str, Enum):
    admin = "admin"
    trader = "trader"
    viewer = "viewer"


class Direction(str, Enum):
    buy = "buy"
    sell = "sell"


class OrderSide(str, Enum):
    buy = "buy"
    sell = "sell"


class OrderStatus(str, Enum):
    pending = "pending"
    filled = "filled"
    rejected = "rejected"
    cancelled = "cancelled"


class PositionStatus(str, Enum):
    open = "open"
    closed = "closed"


class SignalStatus(str, Enum):
    new = "new"
    acted = "acted"
    blocked = "blocked"
