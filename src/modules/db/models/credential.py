"""Encrypted credential storage.

``user_id = NULL`` marks a global/system-default credential. The stored value is
always ciphertext produced by ``modules/encryption`` — never plaintext.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Credential(Base, TimestampMixin):
    __tablename__ = "credentials"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_credential_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
