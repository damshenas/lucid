"""Per-user daily loss tracking (UTC calendar day) for the optional risk gate."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class DailyLoss(Base, TimestampMixin):
    __tablename__ = "daily_losses"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_daily_loss_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    loss_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
