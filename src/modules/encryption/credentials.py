"""Credential cascade: resolve encrypted secrets for a user with system-default fallback.

Resolution for ``get_for_user(key, user_id)`` (per plan.md):
1. If the user has ``use_default_credentials = True`` -> the global credential.
2. Else if a user-specific credential exists -> that one.
3. Else fall back to the global credential.
4. Else raise ``CredentialNotConfiguredError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.db.repositories.credential import CredentialRepository
from src.modules.db.repositories.user import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from . import Encryptor


class CredentialNotConfiguredError(Exception):
    """Raised when no credential can be resolved for a key."""


class CredentialManager:
    def __init__(self, session: AsyncSession, encryptor: Encryptor) -> None:
        self._creds = CredentialRepository(session)
        self._users = UserRepository(session)
        self._encryptor = encryptor

    async def set_for_user(self, key: str, value: str, user_id: int | None = None) -> None:
        """Encrypt and upsert a credential. ``user_id=None`` sets a global default."""
        await self._creds.upsert(key, self._encryptor.encrypt(value), user_id)

    async def get_for_user(self, key: str, user_id: int | None) -> str:
        user = await self._users.get_by_id(user_id) if user_id is not None else None

        if user is not None and user.use_default_credentials:
            cred = await self._creds.get(key, None)
            if cred is not None:
                return self._encryptor.decrypt(cred.value_encrypted)
            raise CredentialNotConfiguredError(f"global credential '{key}' not configured")

        own = await self._creds.get(key, user_id)
        if own is not None:
            return self._encryptor.decrypt(own.value_encrypted)

        glob = await self._creds.get(key, None)
        if glob is not None:
            return self._encryptor.decrypt(glob.value_encrypted)

        raise CredentialNotConfiguredError(f"credential '{key}' not configured")
