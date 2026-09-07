"""Trading212 REST client and broker adapter.

Retry-with-backoff and per-request timeout. An optional circuit breaker can be added
per endpoint later if a specific endpoint proves flaky — not enforced system-wide.

The ``httpx.AsyncClient`` is injectable so tests can supply a ``MockTransport`` with no
real network calls.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx

from src.conf.schema import AssetClass
from src.modules.broker.base import (
    AccountSummary,
    Broker,
    BrokerError,
    BrokerPosition,
    OrderResult,
)
from src.modules.logger import get_logger

# Trading212 uses a single API credential pair (key_id + secret_key), sent as HTTP
# Basic auth, that works against both environments — which account it hits is
# determined entirely by the base URL, not a separate paper credential. These base
# URLs are fixed platform endpoints, not user-supplied config.
DEMO_BASE_URL = "https://demo.trading212.com"
LIVE_BASE_URL = "https://live.trading212.com"

REQUIRED_CONFIG = ["key_id", "secret_key"]
OPTIONAL_CONFIG = {"timeout_seconds": 10.0, "retry_attempts": 3, "backoff_base": 0.2}

# Trading212 requires the full instrument ticker (e.g. "AAPL_US_EQ"), not the plain
# symbol Lucid uses everywhere else (price storage, watchlist, positions). When more
# than one instrument matches a plain symbol (e.g. multiple listings), prefer common
# stock over ETF. Lower rank = preferred.
_SUFFIX_PRIORITY: dict[str, int] = {"_US_EQ": 0, "_US_ETF": 1}

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_logger = get_logger("com.trading212")


class Trading212Error(BrokerError):
    pass


class Trading212Client:
    def __init__(
        self,
        key_id: str,
        secret_key: str,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        retry_attempts: int = 3,
        backoff_base: float = 0.2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not key_id or not secret_key or not base_url:
            raise Trading212Error("key_id, secret_key and base_url are required")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._retry_attempts = max(1, retry_attempts)
        self._backoff_base = backoff_base
        auth = base64.b64encode(f"{key_id}:{secret_key}".encode()).decode()
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Basic {auth}"},
            timeout=timeout_seconds,
        )
        self._instruments_cache: list[dict[str, Any]] | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                response = await self._client.request(method, path, **kwargs)
                if response.status_code in _RETRYABLE_STATUS:
                    raise Trading212Error(f"retryable status {response.status_code}")
                response.raise_for_status()
                if response.content:
                    return response.json()
                return None
            except (httpx.TransportError, httpx.TimeoutException, Trading212Error) as exc:
                last_exc = exc
                if attempt < self._retry_attempts:
                    await asyncio.sleep(self._backoff_base * (2 ** (attempt - 1)))
                    continue
            except httpx.HTTPStatusError as exc:
                raise Trading212Error(f"HTTP {exc.response.status_code} for {path}") from exc
        raise Trading212Error(f"request failed after {self._retry_attempts} attempts: {last_exc}")

    async def _get_instruments(self) -> list[dict[str, Any]]:
        if self._instruments_cache is None:
            data = await self.request("GET", "/api/v0/equity/metadata/instruments") or []
            self._instruments_cache = data if isinstance(data, list) else []
        return self._instruments_cache

    async def resolve_ticker(self, raw: str) -> str:
        """Map a plain symbol (e.g. "AAPL") to Trading212's instrument ticker (e.g.
        "AAPL_US_EQ"). Already-suffixed tickers are returned unchanged. Falls back to
        the raw ticker unchanged if no match is found — let Trading212 reject it with
        a clear error rather than silently failing here."""
        if "_" in raw:
            return raw
        symbol = raw.upper().strip()
        instruments = await self._get_instruments()
        candidates = [i for i in instruments if str(i.get("ticker", "")).split("_")[0] == symbol]
        if not candidates:
            return symbol

        def _rank(ticker: str) -> int:
            for suffix, rank in _SUFFIX_PRIORITY.items():
                if ticker.endswith(suffix):
                    return rank
            return 99

        candidates.sort(key=lambda i: _rank(str(i.get("ticker", ""))))
        return str(candidates[0]["ticker"])


class Trading212Broker(Broker):
    name = "trading212"

    def __init__(self, client: Trading212Client, *, paper: bool = False) -> None:
        self._client = client
        self._paper = paper

    async def place_market_order(
        self, ticker: str, quantity: float, *, asset_class: str = AssetClass.equity.value
    ) -> OrderResult:
        instrument_ticker = await self._client.resolve_ticker(ticker)
        payload = {"ticker": instrument_ticker, "quantity": quantity}
        data = await self._client.request("POST", "/api/v0/equity/orders/market", json=payload)
        data = data or {}
        return OrderResult(
            ticker=ticker,
            quantity=quantity,
            status=str(data.get("status", "pending")).lower(),
            broker_order_id=str(data["id"]) if data.get("id") is not None else None,
            avg_price=data.get("fillPrice"),
            paper=self._paper,
        )

    async def get_positions(self) -> list[BrokerPosition]:
        data = await self._client.request("GET", "/api/v0/equity/positions") or []
        positions = []
        for item in data:
            # Trading212 nests the ticker inside "instrument" rather than returning
            # it top-level; normalize back to the plain symbol used everywhere else
            # in Lucid (e.g. "AAPL_US_EQ" -> "AAPL").
            raw_ticker = item.get("ticker") or (item.get("instrument") or {}).get("ticker", "")
            positions.append(
                BrokerPosition(
                    ticker=str(raw_ticker).split("_")[0],
                    quantity=float(item.get("quantity", 0.0)),
                    avg_price=float(item.get("averagePricePaid", 0.0)),
                    market_price=item.get("currentPrice"),
                )
            )
        return positions

    async def get_account_summary(self) -> AccountSummary:
        data = await self._client.request("GET", "/api/v0/equity/account/summary") or {}
        cash = data.get("cash") or {}
        cash_available = float(cash.get("availableToTrade", 0.0))
        equity = data.get("totalValue")
        return AccountSummary(
            cash=cash_available,
            equity=float(equity) if equity is not None else cash_available,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await self._client.request("DELETE", f"/api/v0/equity/orders/{broker_order_id}")
            return True
        except Trading212Error as exc:
            _logger.warning("cancel_order failed for %s: %s", broker_order_id, exc)
            return False

    async def get_order_status(self, broker_order_id: str) -> OrderResult:
        data = await self._client.request("GET", f"/api/v0/equity/orders/{broker_order_id}") or {}
        raw_ticker = data.get("ticker") or (data.get("instrument") or {}).get("ticker", "")
        return OrderResult(
            ticker=str(raw_ticker).split("_")[0],
            quantity=float(data.get("quantity", 0.0) or 0.0),
            status=str(data.get("status", "pending")).lower(),
            broker_order_id=broker_order_id,
            avg_price=data.get("fillPrice"),
            paper=self._paper,
        )


__all__ = [
    "DEMO_BASE_URL",
    "LIVE_BASE_URL",
    "OPTIONAL_CONFIG",
    "REQUIRED_CONFIG",
    "Trading212Broker",
    "Trading212Client",
    "Trading212Error",
]
