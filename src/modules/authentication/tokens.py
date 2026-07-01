"""JWT access/refresh token creation and validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

_ALGORITHM = "HS256"


class TokenError(Exception):
    """Raised when a token is invalid or expired."""


class TokenService:
    """Issues and validates HS256 JWTs.

    Required: ``secret``, ``access_expiry_minutes``.
    Optional: ``refresh_expiry_days``.
    """

    def __init__(
        self,
        secret: str,
        *,
        access_expiry_minutes: int = 30,
        refresh_expiry_days: int = 7,
    ) -> None:
        if not secret:
            raise TokenError("JWT secret must not be empty")
        self._secret = secret
        self._access_expiry = timedelta(minutes=access_expiry_minutes)
        self._refresh_expiry = timedelta(days=refresh_expiry_days)

    def _create(self, subject: str, token_type: str, ttl: timedelta, extra: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": subject,
            "type": token_type,
            "iat": now,
            "exp": now + ttl,
            **extra,
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def create_access_token(self, subject: str, **extra: Any) -> str:
        return self._create(subject, "access", self._access_expiry, extra)

    def create_refresh_token(self, subject: str, **extra: Any) -> str:
        return self._create(subject, "refresh", self._refresh_expiry, extra)

    def decode(self, token: str, *, expected_type: str | None = None) -> dict[str, Any]:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("token expired") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenError("invalid token") from exc
        if expected_type is not None and payload.get("type") != expected_type:
            raise TokenError(f"expected {expected_type} token")
        return payload
