"""Barchart connector. Returns a normalized opinion/signal for a ticker."""

from __future__ import annotations

from typing import Any

import httpx

from .._provider import HttpDataProvider

REQUIRED_CONFIG = ["base_url"]
OPTIONAL_CONFIG = {"api_key": None, "timeout_seconds": 10.0}


class BarchartConnector:
    source = "barchart"

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._provider = HttpDataProvider(
            self.source, base_url, api_key=api_key, timeout_seconds=timeout_seconds, client=client
        )

    async def fetch_opinion(self, ticker: str) -> dict[str, Any]:
        raw = await self._provider.get_json(f"/opinion/{ticker}")
        return {"source": self.source, "ticker": ticker, "opinion": raw.get("opinion"), "raw": raw}

    async def aclose(self) -> None:
        await self._provider.aclose()


__all__ = ["BarchartConnector", "OPTIONAL_CONFIG", "REQUIRED_CONFIG"]
