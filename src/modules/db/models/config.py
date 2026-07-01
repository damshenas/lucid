"""Persisted config values across all non-default resolution layers.

A single row can represent any of the DB layers via nullable scoping columns:

- ``user_id`` NULL, ``asset_class`` NULL  -> global override
- ``user_id`` NULL, ``asset_class`` set   -> asset-class-scoped override
- ``user_id`` set,  ``asset_class`` NULL  -> per-user (all asset classes)
- ``user_id`` set,  ``asset_class`` set   -> per-user + asset-class

Uniqueness for rows with NULL scope columns is enforced by the repository upsert,
since SQL treats NULLs as distinct in unique constraints.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class UserConfig(Base, TimestampMixin):
    __tablename__ = "user_config"
    __table_args__ = (
        UniqueConstraint("user_id", "asset_class", "key", name="uq_user_config_scope_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    asset_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    key: Mapped[str] = mapped_column(String(150), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
