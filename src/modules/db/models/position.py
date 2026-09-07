"""Open/closed trading positions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import AssetClass, Base, PositionStatus, TimestampMixin


class Position(Base, TimestampMixin):
    __tablename__ = "positions"
    # Unique only among OPEN rows (scoped by asset_class too) — a partial index so a
    # closed position never blocks reopening the same ticker, and the same ticker can
    # be held open simultaneously in two different asset classes (e.g. BTCUSD as both
    # crypto and fx). Closed rows for the same (user, ticker, asset_class) may repeat
    # freely, preserving full round-trip history.
    __table_args__ = (
        Index(
            "uq_position_open_user_ticker_assetclass",
            "user_id",
            "ticker",
            "asset_class",
            unique=True,
            sqlite_where=text("status = 'open'"),
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(20), default=AssetClass.equity.value, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Highest price observed since the position was opened — a tiered/trailing sell
    # strategy (strategies/sell/trailing_stop.py) trails its stop from this peak, not
    # from avg_price, so it actually gives back a bounded amount from the peak rather
    # than only ever protecting the original entry. Bumped by
    # PositionRepository.bump_high_water_mark; never decreases. Nullable only for a
    # pre-migration row — callers treat None as "use avg_price".
    high_water_mark: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default=PositionStatus.open.value, nullable=False)
    # Set once a tiered sell strategy (e.g. strategies/sell/trailing_stop.py) has
    # fired its first/second profit-take tier for this position, so it never re-fires
    # the same tier again on a later evaluation — see ExecutionEngine.handle_sell and
    # SellSignalEvent.profit_tier. Always False on a freshly (re)opened position.
    profit_tier1_taken: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    profit_tier2_taken: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
