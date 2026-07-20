"""TradingView connector — POSTs directly to TradingView's real public scanner API
(the same undocumented endpoint the legacy ``dealer`` app used,
``integration/web/tradingview.py``) for US-stock buy recommendations. No API key or
configurable ``base_url`` — it's a fixed, unauthenticated public endpoint.
"""

from __future__ import annotations

from typing import Any

import httpx

from .._retry import DEFAULT_BACKOFF_BASE, DEFAULT_RETRY_ATTEMPTS, with_retry

REQUIRED_CONFIG: list[str] = []
OPTIONAL_CONFIG: dict[str, Any] = {"timeout_seconds": 20.0, "max_results": 50}

_SCAN_URL = "https://scanner.tradingview.com/america/scan"


def _scanner_payload(max_results: int) -> dict[str, Any]:
    return {
        "columns": ["name", "close", "change", "volume", "Recommend.All", "RSI"],
        # Pre-filtered server-side to a positive composite technical rating (same
        # filter the legacy dealer app used) — every result is already buy-leaning.
        "filter": [
            {"left": "Recommend.All", "operation": "greater", "right": 0.3},
            {"left": "close", "operation": "greater", "right": 5.0},
            {"left": "volume", "operation": "greater", "right": 500000},
            {"left": "is_primary", "operation": "equal", "right": True},
        ],
        "options": {"lang": "en"},
        "range": [0, max_results],
        "sort": {"sortBy": "Recommend.All", "sortOrder": "desc"},
        "symbols": {"query": {"types": ["stock"]}},
        "markets": ["america"],
    }


class TradingViewConnector:
    source = "tradingview"

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_results: int = 50,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._max_results = max_results

    async def fetch_all_technicals(self) -> list[dict[str, Any]]:
        """Every US stock TradingView's scanner currently flags with a positive
        composite technical rating. Transient transport/timeout errors are retried
        with backoff first (matches the old dealer app's tenacity-based retry); a
        persistent HTTP error (e.g. a 429) propagates to the caller."""
        resp = await with_retry(
            lambda: self._client.post(_SCAN_URL, json=_scanner_payload(self._max_results)),
            retry_attempts=DEFAULT_RETRY_ATTEMPTS,
            backoff_base=DEFAULT_BACKOFF_BASE,
            retryable_exceptions=(httpx.TransportError, httpx.TimeoutException),
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[dict[str, Any]] = []
        for row in data.get("data", []):
            d = row.get("d") or []
            if len(d) < 5:
                continue
            ticker_raw = d[0]
            if not ticker_raw or not isinstance(ticker_raw, str):
                continue
            # TradingView returns "NASDAQ:AAPL"/"NYSE:MSFT" — strip the exchange prefix.
            ticker = (ticker_raw.split(":")[-1] if ":" in ticker_raw else ticker_raw).strip().upper()
            if not ticker:
                continue
            try:
                recommendation = float(d[4]) if d[4] is not None else None
            except (TypeError, ValueError):
                recommendation = None
            results.append(
                {
                    "source": self.source,
                    "ticker": ticker,
                    "recommendation": recommendation,
                    "raw": {"ticker": ticker, "row": d},
                }
            )
        return results

    async def fetch_technicals(self, ticker: str) -> dict[str, Any]:
        """Per-ticker convenience lookup — TradingView's scanner has no
        single-ticker endpoint, so this reuses the same scan and reports no
        opinion if the ticker isn't currently in the pre-filtered result set."""
        match = next(
            (item for item in await self.fetch_all_technicals() if item["ticker"] == ticker.upper()), None
        )
        if match is not None:
            return match
        return {"source": self.source, "ticker": ticker.upper(), "recommendation": None, "raw": None}

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["OPTIONAL_CONFIG", "REQUIRED_CONFIG", "TradingViewConnector"]
