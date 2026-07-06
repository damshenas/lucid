"""Price watchlist and per-ticker fetch bookkeeping (global)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import AssetClass, Base, TimestampMixin


class PriceWatchlist(Base, TimestampMixin):
    __tablename__ = "price_watchlist"
    __table_args__ = (
        CheckConstraint("poll_interval IN ('1m', '1h')", name="ck_price_watchlist_poll_interval"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    asset_class: Mapped[str] = mapped_column(String(20), default=AssetClass.equity.value, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Intraday granularity this ticker is polled at (Settings > Price > Watchlist UI —
    # click a chip to cycle it): "1m" (green) or "1h" (blue, the default). Independent
    # of the always-on daily ("1d") fetch every watchlist ticker gets regardless of
    # this value — see TradingRuntime.register_jobs/._watchlist_by_poll_interval in
    # src/api/runtime.py.
    poll_interval: Mapped[str] = mapped_column(String(10), default="1h", nullable=False)


class PriceFetchLog(Base):
    __tablename__ = "price_fetch_log"
    __table_args__ = (UniqueConstraint("ticker", "interval", name="uq_price_fetch_ticker_interval"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    interval: Mapped[str] = mapped_column(String(20), nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
