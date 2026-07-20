"""Barchart connector — DISABLED placeholder.

The legacy ``dealer`` app's real Barchart Opinion data (``integration/web/
barchart.py``) requires either an internal JSON API reached via a scraped
session/XSRF-token cookie dance, or a headless-browser (Playwright) HTML fallback
— neither implemented here (see finviz/tradingview for the two sources that don't
need one). Calls raise ``DisabledConnectorError`` until that's added and this is
re-enabled.
"""

from __future__ import annotations

DISABLED = True
REQUIRED_CONFIG: list[str] = []
OPTIONAL_CONFIG: dict[str, object] = {}


class DisabledConnectorError(RuntimeError):
    pass


class BarchartConnector:
    enabled = False
    source = "barchart"

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def fetch_opinion(self, ticker: str) -> dict[str, object]:
        raise DisabledConnectorError("barchart connector is disabled (needs session/XSRF or a headless browser)")

    async def fetch_all_opinions(self) -> list[dict[str, object]]:
        raise DisabledConnectorError("barchart connector is disabled (needs session/XSRF or a headless browser)")

    async def aclose(self) -> None:
        pass


__all__ = ["BarchartConnector", "DISABLED", "DisabledConnectorError", "OPTIONAL_CONFIG", "REQUIRED_CONFIG"]
