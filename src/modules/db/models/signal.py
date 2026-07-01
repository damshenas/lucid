"""Trading signals and their post-close outcomes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import AssetClass, Base, SignalStatus, TimestampMixin


class Signal(Base, TimestampMixin):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    asset_class: Mapped[str] = mapped_column(String(20), default=AssetClass.equity.value, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default=SignalStatus.new.value, nullable=False)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SignalOutcome(Base, TimestampMixin):
    __tablename__ = "signal_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profitable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
