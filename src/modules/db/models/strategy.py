"""Registry of discovered single-file strategies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class StrategyRegistry(Base, TimestampMixin):
    __tablename__ = "strategy_registry"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Self-declared by the strategy file itself (module-level ``FEATURES`` list, e.g.
    # ["signals"]) — drives which extra info the UI's per-strategy page shows (see
    # src/modules/strategy/loader.py and pages/StrategyDetail.tsx). Not every strategy
    # produces the same kind of data, so this isn't a fixed/shared set of fields.
    features: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
