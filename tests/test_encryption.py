"""M2: encryption round-trip and the credential cascade."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.encryption import (
    CredentialManager,
    CredentialNotConfiguredError,
    EncryptionError,
    Encryptor,
    generate_key,
)
from src.modules.db.repositories.user import UserRepository


def _encryptor() -> Encryptor:
    import base64

    return Encryptor(base64.b64decode(generate_key()))


def test_encrypt_decrypt_round_trip() -> None:
    enc = _encryptor()
    token = enc.encrypt("super-secret-api-key")
    assert token != "super-secret-api-key"
    assert enc.decrypt(token) == "super-secret-api-key"


def test_wrong_key_fails() -> None:
    token = _encryptor().encrypt("x")
    with pytest.raises(EncryptionError):
        _encryptor().decrypt(token)


async def test_cascade_user_specific(session: AsyncSession) -> None:
    users = UserRepository(session)
    user = await users.create(username="t", password_hash="x", role="trader")
    mgr = CredentialManager(session, _encryptor())

    await mgr.set_for_user("t212_key", "USER_KEY", user_id=user.id)
    await mgr.set_for_user("t212_key", "GLOBAL_KEY", user_id=None)

    assert await mgr.get_for_user("t212_key", user.id) == "USER_KEY"


async def test_cascade_falls_back_to_global(session: AsyncSession) -> None:
    users = UserRepository(session)
    user = await users.create(username="t", password_hash="x", role="trader")
    mgr = CredentialManager(session, _encryptor())

    await mgr.set_for_user("t212_key", "GLOBAL_KEY", user_id=None)
    assert await mgr.get_for_user("t212_key", user.id) == "GLOBAL_KEY"


async def test_cascade_use_default_prefers_global(session: AsyncSession) -> None:
    users = UserRepository(session)
    user = await users.create(
        username="t", password_hash="x", role="trader", use_default_credentials=True
    )
    mgr = CredentialManager(session, _encryptor())

    await mgr.set_for_user("t212_key", "USER_KEY", user_id=user.id)
    await mgr.set_for_user("t212_key", "GLOBAL_KEY", user_id=None)

    assert await mgr.get_for_user("t212_key", user.id) == "GLOBAL_KEY"


async def test_cascade_not_configured_raises(session: AsyncSession) -> None:
    users = UserRepository(session)
    user = await users.create(username="t", password_hash="x", role="trader")
    mgr = CredentialManager(session, _encryptor())

    with pytest.raises(CredentialNotConfiguredError):
        await mgr.get_for_user("missing_key", user.id)
