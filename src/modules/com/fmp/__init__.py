"""Financial Modeling Prep (FMP) connector — fundamentals-based rating and
analyst grade consensus.

Free tier: 250 calls/day, API key only, no credit card. Fixed public REST base
URL (``https://financialmodelingprep.com/stable``) — the only credential
needed is the API key itself (sent as the ``apikey`` query parameter, FMP's
documented auth style), unlike a generic ``<source>_base_url``-configurable
connector.

Two independent signals are exposed here (each registered as its own source in
``src.modules.signal.sources``, sharing the same ``fmp_api_key`` credential):

- ``fetch_rating`` -> ``GET /ratings-snapshot?symbol=X``: a DCF/ROE/ROA/D-E/P-E/
  P-B-based fundamentals score. Confirmed response shape (FMP's stable API,
  2026): ``{"symbol", "rating" (letter grade e.g. "B"), "overallScore" (1-5,
  5=best), "discountedCashFlowScore", "returnOnEquityScore", ...}`` — note this
  is FMP's *current* "stable" endpoint; it no longer includes the old v3
  endpoint's plain-English "Strong Buy" text field, so ``overallScore``
  (1-5) is mapped straight to the standard 5-level rating instead.
- ``fetch_grades_consensus`` -> ``GET /grades-consensus?symbol=X``: total
  counts of strong buy/buy/hold/sell/strong sell analyst grades outstanding
  for the ticker — the "analyst consensus" flavor of signal, collapsed via
  ``rating.rating_from_vote_counts`` the same way Finnhub's recommendation
  trends are.

Neither endpoint has a bulk "every currently-rated ticker" equivalent on the
free tier, so this connector is per-ticker only (no ``discover_*`` method).
"""

from __future__ import annotations

from typing import Any

import httpx

from .._retry import DEFAULT_BACKOFF_BASE, DEFAULT_RETRY_ATTEMPTS, with_retry

REQUIRED_CONFIG: list[str] = ["api_key"]
OPTIONAL_CONFIG: dict[str, Any] = {"timeout_seconds": 15.0}

_BASE_URL = "https://financialmodelingprep.com/stable"

# FMP's ratings-snapshot overallScore is a 1-5 quintile (5=best) rather than a
# -1..+1 composite — map it straight to the standard 5-level rating.
_OVERALL_SCORE_RATING: dict[int, str] = {
    5: "strong_buy",
    4: "buy",
    3: "neutral",
    2: "sell",
    1: "strong_sell",
}


class FMPConnector:
    source = "fmp"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(base_url=_BASE_URL, timeout=timeout_seconds)

    async def _get(self, path: str, ticker: str) -> Any:
        resp = await with_retry(
            lambda: self._client.get(path, params={"symbol": ticker.upper(), "apikey": self._api_key}),
            retry_attempts=DEFAULT_RETRY_ATTEMPTS,
            backoff_base=DEFAULT_BACKOFF_BASE,
            retryable_exceptions=(httpx.TransportError, httpx.TimeoutException),
        )
        resp.raise_for_status()
        return resp.json()

    async def fetch_rating(self, ticker: str) -> dict[str, Any]:
        """Fundamentals-based rating snapshot for one ticker."""
        rows = await self._get("/ratings-snapshot", ticker)
        row = (rows or [{}])[0] if isinstance(rows, list) else (rows or {})
        return {
            "source": self.source,
            "ticker": ticker.upper(),
            "rating": row.get("rating"),
            "overallScore": row.get("overallScore"),
            "raw": row or None,
        }

    async def fetch_grades_consensus(self, ticker: str) -> dict[str, Any]:
        """Analyst grade consensus counts for one ticker."""
        rows = await self._get("/grades-consensus", ticker)
        row = (rows or [{}])[0] if isinstance(rows, list) else (rows or {})
        return {
            "source": "fmp_grades",
            "ticker": ticker.upper(),
            "strongBuy": row.get("strongBuy", 0),
            "buy": row.get("buy", 0),
            "hold": row.get("hold", 0),
            "sell": row.get("sell", 0),
            "strongSell": row.get("strongSell", 0),
            "raw": row or None,
        }

    async def aclose(self) -> None:
        await self._client.aclose()


def rating_from_overall_score(score: Any) -> str | None:
    try:
        return _OVERALL_SCORE_RATING.get(int(score))
    except (TypeError, ValueError):
        return None


__all__ = ["FMPConnector", "OPTIONAL_CONFIG", "REQUIRED_CONFIG", "rating_from_overall_score"]
