"""Shared HTTP helper for data-provider connectors.

The ``httpx.AsyncClient`` is injectable so tests can use a ``MockTransport`` with no real
network calls.
"""

from __future__ import annotations

from typing import Any

import httpx


class HttpDataProvider:
    def __init__(
        self,
        source: str,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.source = source
        headers = {"Authorization": api_key} if api_key else {}
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_seconds
        )

    async def get_json(self, path: str, **kwargs: Any) -> Any:
        response = await self._client.get(path, **kwargs)
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
