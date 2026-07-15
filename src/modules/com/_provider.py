"""Shared HTTP helper for data-provider connectors.

The ``httpx.AsyncClient`` is injectable so tests can use a ``MockTransport`` with no real
network calls. Requests are retried with exponential backoff on transport errors,
timeouts, or a retryable HTTP status (429 rate-limit, or a 5xx) — see ``_retry.py``.
"""

from __future__ import annotations

from typing import Any

import httpx

from ._retry import DEFAULT_BACKOFF_BASE, DEFAULT_RETRY_ATTEMPTS, with_retry

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RetryableStatusError(Exception):
    """Raised internally when a response's status is in ``_RETRYABLE_STATUS``."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"retryable status {status_code}")


class HttpDataProvider:
    def __init__(
        self,
        source: str,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
    ) -> None:
        self.source = source
        headers = {"Authorization": api_key} if api_key else {}
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_seconds
        )
        self._retry_attempts = retry_attempts
        self._backoff_base = backoff_base

    async def get_json(self, path: str, **kwargs: Any) -> Any:
        async def _attempt() -> Any:
            response = await self._client.get(path, **kwargs)
            if response.status_code in _RETRYABLE_STATUS:
                raise RetryableStatusError(response.status_code)
            response.raise_for_status()
            return response.json()

        return await with_retry(
            _attempt,
            retry_attempts=self._retry_attempts,
            backoff_base=self._backoff_base,
            retryable_exceptions=(httpx.TransportError, httpx.TimeoutException, RetryableStatusError),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
