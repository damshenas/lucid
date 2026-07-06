"""Strategy decision log — one row per *change* in a strategy's evaluation outcome
for a given (user, ticker), whether or not it decided to act. This is what powers
the "why or why not" decision list on each active strategy's page (see
src/api/runtime.py TradingRuntime._record_decision and pages/StrategyDetail.tsx) —
distinct from ``signals`` (src/modules/db/models/signal.py), which only ever
records a row when a strategy actually decides to act.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import AssetClass, Base, TimestampMixin


class StrategyDecisionLog(Base, TimestampMixin):
    __tablename__ = "strategy_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(20), default=AssetClass.equity.value, nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    acted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
