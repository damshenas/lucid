"""Finviz connector. Returns normalized fundamental/technical metrics for a ticker."""

from __future__ import annotations

from typing import Any

import httpx

from .._provider import HttpDataProvider

REQUIRED_CONFIG = ["base_url"]
OPTIONAL_CONFIG = {"api_key": None, "timeout_seconds": 10.0}


class FinvizConnector:
    source = "finviz"

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

    async def fetch_metrics(self, ticker: str) -> dict[str, Any]:
        raw = await self._provider.get_json(f"/quote/{ticker}")
        return {"source": self.source, "ticker": ticker, "metrics": raw.get("metrics", {}), "raw": raw}

    async def fetch_screener(self) -> list[dict[str, Any]]:
        """Every ticker Finviz's own screen currently has an opinion on — used for
        candidate *discovery* (no predefined ticker list required), unlike
        ``fetch_metrics`` above which needs a ticker already in hand. Expects
        ``GET {base_url}/screener`` -> ``{"items": [{"ticker": ..., "metrics":
        {...}}, ...]}``, one item per rated ticker, each shaped like a single
        ``fetch_metrics`` result."""
        raw = await self._provider.get_json("/screener")
        return [
            {"source": self.source, "ticker": item["ticker"], "metrics": item.get("metrics", {}), "raw": item}
            for item in raw.get("items", [])
            if item.get("ticker")
        ]

    async def aclose(self) -> None:
        await self._provider.aclose()


__all__ = ["FinvizConnector", "OPTIONAL_CONFIG", "REQUIRED_CONFIG"]
