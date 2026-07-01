"""AES-256-GCM encryption for secrets stored in the database.

The key comes only from the ``LUCID_ENCRYPTION_KEY`` environment variable (base64,
32 bytes) — never from a config file. Ciphertext is ``base64(nonce || ct)``.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENV_VAR = "LUCID_ENCRYPTION_KEY"
_NONCE_BYTES = 12
_KEY_BYTES = 32


class EncryptionError(Exception):
    """Raised for key/ciphertext problems."""


class Encryptor:
    """Symmetric encrypt/decrypt of UTF-8 strings with AES-256-GCM."""

    def __init__(self, key: bytes) -> None:
        if len(key) != _KEY_BYTES:
            raise EncryptionError(f"key must be {_KEY_BYTES} bytes, got {len(key)}")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            raw = base64.b64decode(token)
            nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
            return self._aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - normalize crypto/decoding errors
            raise EncryptionError("failed to decrypt token") from exc


def generate_key() -> str:
    """Return a fresh base64-encoded 32-byte key (for setup scripts)."""
    return base64.b64encode(os.urandom(_KEY_BYTES)).decode("ascii")


def load_key_from_env(var: str = ENV_VAR) -> bytes:
    value = os.environ.get(var)
    if not value:
        raise EncryptionError(f"{var} is not set")
    try:
        key = base64.b64decode(value)
    except Exception as exc:  # noqa: BLE001
        raise EncryptionError(f"{var} is not valid base64") from exc
    if len(key) != _KEY_BYTES:
        raise EncryptionError(f"{var} must decode to {_KEY_BYTES} bytes")
    return key


def encryptor_from_env(var: str = ENV_VAR) -> Encryptor:
    return Encryptor(load_key_from_env(var))


def reencrypt(token: str, old: Encryptor, new: Encryptor) -> str:
    """Key-rotation helper: decrypt with the old key, re-encrypt with the new."""
    return new.encrypt(old.decrypt(token))


from .credentials import CredentialManager, CredentialNotConfiguredError  # noqa: E402

__all__ = [
    "CredentialManager",
    "CredentialNotConfiguredError",
    "Encryptor",
    "EncryptionError",
    "encryptor_from_env",
    "generate_key",
    "load_key_from_env",
    "reencrypt",
]
