"""Zacks connector — DISABLED placeholder.

The legacy ``dealer`` app's real Zacks Rank data (``integration/web/zacks.py``)
requires scraping zacks.com from behind Cloudflare/Incapsula anti-bot protection —
reliably only via a headless browser (Playwright), which this repo doesn't run (see
finviz/tradingview for the two sources that don't need one). Calls raise
``DisabledConnectorError`` until that's added and this is re-enabled.
"""

from __future__ import annotations

DISABLED = True
REQUIRED_CONFIG: list[str] = []
OPTIONAL_CONFIG: dict[str, object] = {}


class DisabledConnectorError(RuntimeError):
    pass


class ZacksConnector:
    enabled = False
    source = "zacks"

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def fetch_rank(self, ticker: str) -> dict[str, object]:
        raise DisabledConnectorError("zacks connector is disabled (needs a headless browser)")

    async def fetch_ranks(self) -> list[dict[str, object]]:
        raise DisabledConnectorError("zacks connector is disabled (needs a headless browser)")

    async def aclose(self) -> None:
        pass


__all__ = ["DISABLED", "DisabledConnectorError", "OPTIONAL_CONFIG", "REQUIRED_CONFIG", "ZacksConnector"]
