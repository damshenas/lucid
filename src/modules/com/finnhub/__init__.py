"""Finnhub connector — Recommendation Trends (analyst consensus buckets).

Free tier: 60 calls/min, instant API key, no credit card (per Finnhub's public
docs). Fixed public REST base URL; the only credential needed is the API key
itself (sent as the ``token`` query parameter — Finnhub's documented auth
style), unlike a generic ``<source>_base_url``-configurable connector.

Endpoint: ``GET /stock/recommendation?symbol=TICKER`` returns a list of monthly
buckets, most-recent first — each with ``strongBuy``/``buy``/``hold``/``sell``/
``strongSell`` analyst counts for that period. This is the "analyst consensus"
flavor of signal (as opposed to a pure technical or fundamentals score) — see
``src.modules.signal.rating.rating_from_vote_counts`` for how these counts are
collapsed into the standard 5-level rating.

No bulk "every currently-rated ticker" endpoint exists on Finnhub's free tier,
so this connector is per-ticker only (no ``discover_*`` method) — usable by any
strategy that already has a candidate ticker list (watchlist/open positions),
not by discovery-based strategies like ``signal_follow``.
"""

from __future__ import annotations

from typing import Any

import httpx

from .._retry import DEFAULT_BACKOFF_BASE, DEFAULT_RETRY_ATTEMPTS, with_retry

REQUIRED_CONFIG: list[str] = ["api_key"]
OPTIONAL_CONFIG: dict[str, Any] = {"timeout_seconds": 15.0}

_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubConnector:
    source = "finnhub"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=_BASE_URL, headers={"X-Finnhub-Token": api_key}, timeout=timeout_seconds
        )

    async def fetch_recommendation(self, ticker: str) -> dict[str, Any]:
        """Latest analyst recommendation-trend bucket for one ticker."""
        resp = await with_retry(
            lambda: self._client.get("/stock/recommendation", params={"symbol": ticker.upper()}),
            retry_attempts=DEFAULT_RETRY_ATTEMPTS,
            backoff_base=DEFAULT_BACKOFF_BASE,
            retryable_exceptions=(httpx.TransportError, httpx.TimeoutException),
        )
        resp.raise_for_status()
        rows = resp.json() or []
        latest = rows[0] if rows else {}
        return {
            "source": self.source,
            "ticker": ticker.upper(),
            "strongBuy": latest.get("strongBuy", 0),
            "buy": latest.get("buy", 0),
            "hold": latest.get("hold", 0),
            "sell": latest.get("sell", 0),
            "strongSell": latest.get("strongSell", 0),
            "period": latest.get("period"),
            "raw": latest or None,
        }

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["FinnhubConnector", "OPTIONAL_CONFIG", "REQUIRED_CONFIG"]
