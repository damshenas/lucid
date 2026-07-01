"""Price watchlist and per-ticker fetch bookkeeping (global)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import AssetClass, Base, TimestampMixin


class PriceWatchlist(Base, TimestampMixin):
    __tablename__ = "price_watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    asset_class: Mapped[str] = mapped_column(String(20), default=AssetClass.equity.value, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PriceFetchLog(Base):
    __tablename__ = "price_fetch_log"
    __table_args__ = (UniqueConstraint("ticker", "interval", name="uq_price_fetch_ticker_interval"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    interval: Mapped[str] = mapped_column(String(20), nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
