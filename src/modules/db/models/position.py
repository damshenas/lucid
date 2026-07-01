"""Open/closed trading positions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import AssetClass, Base, PositionStatus, TimestampMixin


class Position(Base, TimestampMixin):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_position_user_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(20), default=AssetClass.equity.value, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default=PositionStatus.open.value, nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
