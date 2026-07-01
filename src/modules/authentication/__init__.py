"""JWT-based authentication: password hashing, tokens, and the auth service."""

from __future__ import annotations

from .password import hash_password, verify_password
from .service import (
    AuthError,
    AuthService,
    FirstRunError,
    InvalidCredentialsError,
)
from .tokens import TokenError, TokenService

__all__ = [
    "AuthError",
    "AuthService",
    "FirstRunError",
    "InvalidCredentialsError",
    "TokenError",
    "TokenService",
    "hash_password",
    "verify_password",
]
