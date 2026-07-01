"""Credential repository. Stores ciphertext only; cascade logic lives in encryption."""

from __future__ import annotations

from sqlalchemy import select

from ..models.credential import Credential
from .base import BaseRepository


class CredentialRepository(BaseRepository[Credential]):
    model = Credential

    async def get(self, key: str, user_id: int | None) -> Credential | None:
        stmt = select(Credential).where(Credential.key == key)
        stmt = stmt.where(Credential.user_id.is_(None) if user_id is None else Credential.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, key: str, value_encrypted: str, user_id: int | None = None) -> Credential:
        existing = await self.get(key, user_id)
        if existing is not None:
            existing.value_encrypted = value_encrypted
            await self.session.flush()
            return existing
        return await self.create(user_id=user_id, key=key, value_encrypted=value_encrypted)
