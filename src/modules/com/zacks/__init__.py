"""Zacks connector. Returns a normalized rank/rating for a ticker.

Endpoint paths are provider-specific and configured via ``base_url``; the normalization
contract (the returned dict shape) is what the rest of Lucid depends on.
"""

from __future__ import annotations

from typing import Any

import httpx

from .._provider import HttpDataProvider

REQUIRED_CONFIG = ["base_url"]
OPTIONAL_CONFIG = {"api_key": None, "timeout_seconds": 10.0}


class ZacksConnector:
    source = "zacks"

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

    async def fetch_rank(self, ticker: str) -> dict[str, Any]:
        raw = await self._provider.get_json(f"/rank/{ticker}")
        return {"source": self.source, "ticker": ticker, "rank": raw.get("rank"), "raw": raw}

    async def fetch_ranks(self) -> list[dict[str, Any]]:
        """Every ticker Zacks currently has a rank for — used for candidate
        *discovery* (no predefined ticker list required), unlike ``fetch_rank``
        above which needs a ticker already in hand. Expects ``GET {base_url}/ranks``
        -> ``{"items": [{"ticker": ..., "rank": ...}, ...]}``, one item per ranked
        ticker, each shaped like a single ``fetch_rank`` result."""
        raw = await self._provider.get_json("/ranks")
        return [
            {"source": self.source, "ticker": item["ticker"], "rank": item.get("rank"), "raw": item}
            for item in raw.get("items", [])
            if item.get("ticker")
        ]

    async def aclose(self) -> None:
        await self._provider.aclose()


__all__ = ["OPTIONAL_CONFIG", "REQUIRED_CONFIG", "ZacksConnector"]
