"""Finviz connector — mirrors the legacy ``dealer`` app's actual approach
(``integration/web/finviz.py``): no API key or configurable ``base_url``, just a
direct scrape of Finviz's public screener pages. Finviz has no per-ticker JSON API
at all — every ticker's screener result links to ``quote.ashx?t=TICKER``, a URL
pattern that's been stable for years, so tickers are extracted via that pattern
rather than depending on the screener table's exact column layout (which the old
app's BeautifulSoup table parser did, and which breaks whenever Finviz tweaks its
HTML — a plain link-pattern scan is more resilient for the one thing Lucid actually
needs: which tickers are currently flagged, not their price/volume/sector).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .._retry import DEFAULT_BACKOFF_BASE, DEFAULT_RETRY_ATTEMPTS, with_retry

REQUIRED_CONFIG: list[str] = []
OPTIONAL_CONFIG: dict[str, Any] = {"timeout_seconds": 20.0}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Finviz's built-in "signal" screener views — all bullish/momentum screens, the
# same set the legacy dealer app pulled from (it never used a bearish screen).
_SIGNAL_URLS = {
    "top_gainers": "https://finviz.com/screener.ashx?v=111&s=ta_topgainers",
    "new_high": "https://finviz.com/screener.ashx?v=111&s=ta_newhigh",
    "oversold": "https://finviz.com/screener.ashx?v=111&s=ta_oversold",
    "analyst_upgrades": "https://finviz.com/screener.ashx?v=111&s=n_upgrades",
}

_TICKER_HREF_RE = re.compile(r"quote\.ashx\?t=([A-Z.\-]{1,10})", re.IGNORECASE)


def _extract_tickers(html: str) -> list[str]:
    return sorted({m.group(1).upper() for m in _TICKER_HREF_RE.finditer(html)})


class FinvizConnector:
    source = "finviz"

    def __init__(
        self, *, timeout_seconds: float = 20.0, client: httpx.AsyncClient | None = None
    ) -> None:
        self._client = client or httpx.AsyncClient(
            headers=_HEADERS, timeout=timeout_seconds, follow_redirects=True
        )

    async def fetch_screener(self) -> list[dict[str, Any]]:
        """Every ticker currently on one of Finviz's bullish screens — every result
        here is implicitly "buy" (there's no bearish screen in the set). One screen
        failing (network error, HTML change, or a persistent 429) never blocks the
        others — transient transport/timeout errors are retried with backoff first
        (matches the old dealer app's tenacity-based retry)."""
        seen: dict[str, list[str]] = {}
        for signal_type, url in _SIGNAL_URLS.items():
            try:
                resp = await with_retry(
                    lambda url=url: self._client.get(url),
                    retry_attempts=DEFAULT_RETRY_ATTEMPTS,
                    backoff_base=DEFAULT_BACKOFF_BASE,
                    retryable_exceptions=(httpx.TransportError, httpx.TimeoutException),
                )
                resp.raise_for_status()
            except httpx.HTTPError:
                continue
            for ticker in _extract_tickers(resp.text):
                seen.setdefault(ticker, []).append(signal_type)
        return [
            {
                "source": self.source,
                "ticker": ticker,
                "metrics": {"recommendation": "buy", "signal_types": signal_types},
                "raw": {"ticker": ticker, "signal_types": signal_types},
            }
            for ticker, signal_types in seen.items()
        ]

    async def fetch_metrics(self, ticker: str) -> dict[str, Any]:
        """Per-ticker convenience lookup — Finviz has no per-ticker signal
        endpoint, so this reuses the same screener scrape and reports "buy" only
        if the ticker currently appears on one of the screens above."""
        match = next(
            (item for item in await self.fetch_screener() if item["ticker"] == ticker.upper()), None
        )
        if match is not None:
            return match
        return {"source": self.source, "ticker": ticker.upper(), "metrics": {}, "raw": None}

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["FinvizConnector", "OPTIONAL_CONFIG", "REQUIRED_CONFIG"]
