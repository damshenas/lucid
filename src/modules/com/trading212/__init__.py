"""Trading212 REST client and broker adapter.

Retry-with-backoff and per-request timeout. An optional circuit breaker can be added
per endpoint later if a specific endpoint proves flaky — not enforced system-wide.

The ``httpx.AsyncClient`` is injectable so tests can supply a ``MockTransport`` with no
real network calls.
"""

from __future__ import annotations

import asyncio
import base64
import re
import time
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
# /equity/orders/{id} only covers active orders; once filled/cancelled it 404s and
# the order must be looked up in history instead — cap how many pages we scan.
_HISTORY_LOOKUP_PAGES = 5
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
        # Per-endpoint-template rate-limit state, keyed by "METHOD /normalized/path"
        # (numeric path segments collapsed to "{id}" — Trading212 limits e.g.
        # /equity/orders/{id} as one bucket regardless of the actual order id).
        # Populated from x-ratelimit-remaining/x-ratelimit-reset on every response so
        # a known-exhausted endpoint is waited out before the next call instead of
        # firing it and getting a 429 back.
        self._rate_limit_reset: dict[str, float] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _bucket_key(method: str, path: str) -> str:
        normalized = re.sub(r"/\d+(?=/|$)", "/{id}", path)
        return f"{method.upper()} {normalized}"

    def _record_rate_limit(self, method: str, path: str, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        if remaining is None or reset is None:
            return
        try:
            remaining_n = int(remaining)
            reset_ts = float(reset)
        except ValueError:
            return
        key = self._bucket_key(method, path)
        if remaining_n <= 0:
            self._rate_limit_reset[key] = reset_ts
        else:
            self._rate_limit_reset.pop(key, None)

    async def _wait_for_rate_limit(self, method: str, path: str) -> None:
        reset_ts = self._rate_limit_reset.get(self._bucket_key(method, path))
        if reset_ts is None:
            return
        delay = reset_ts - time.time()
        if delay > 0:
            await asyncio.sleep(delay)

    async def request(
        self, method: str, path: str, *, allow_404: bool = False, **kwargs: Any
    ) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            await self._wait_for_rate_limit(method, path)
            try:
                response = await self._client.request(method, path, **kwargs)
                self._record_rate_limit(method, path, response)
                if allow_404 and response.status_code == 404:
                    return None
                if response.status_code in _RETRYABLE_STATUS:
                    exc = Trading212Error(f"retryable status {response.status_code}")
                    exc.delay = self._retry_delay(response, attempt)
                    raise exc
                response.raise_for_status()
                if response.content:
                    return response.json()
                return None
            except (httpx.TransportError, httpx.TimeoutException, Trading212Error) as exc:
                last_exc = exc
                if attempt < self._retry_attempts:
                    delay = getattr(exc, "delay", None)
                    await asyncio.sleep(
                        delay if delay is not None else self._backoff_base * (2 ** (attempt - 1))
                    )
                    continue
            except httpx.HTTPStatusError as exc:
                body = exc.response.text.strip()[:500]
                detail = f": {body}" if body else ""
                raise Trading212Error(
                    f"HTTP {exc.response.status_code} for {path}{detail}"
                ) from exc
        raise Trading212Error(f"request failed after {self._retry_attempts} attempts: {last_exc}")

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        """Trading212 enforces separate, much tighter rate limits on some
        endpoints (e.g. 6 req/60s on /history/orders) than the default
        exponential backoff assumes — honor the server's ``Retry-After`` header
        when present instead of re-hitting the same window immediately."""
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            try:
                return max(float(retry_after), self._backoff_base)
            except ValueError:
                pass
        return self._backoff_base * (2 ** (attempt - 1))

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
        data = await self._client.request(
            "GET", f"/api/v0/equity/orders/{broker_order_id}", allow_404=True
        )
        if data is None:
            # No longer active (filled/cancelled) — resolve the terminal state from history.
            data = await self._find_in_history(broker_order_id)
            if data is None:
                raise Trading212Error(
                    f"order {broker_order_id} not found in active orders or history"
                )
        raw_ticker = data.get("ticker") or (data.get("instrument") or {}).get("ticker", "")
        return OrderResult(
            ticker=str(raw_ticker).split("_")[0],
            quantity=float(data.get("quantity", 0.0) or 0.0),
            status=str(data.get("status", "pending")).lower(),
            broker_order_id=broker_order_id,
            avg_price=data.get("fillPrice"),
            paper=self._paper,
        )

    async def _find_in_history(self, broker_order_id: str) -> dict[str, Any] | None:
        cursor: str | None = None
        for _ in range(_HISTORY_LOOKUP_PAGES):
            params = {"cursor": cursor} if cursor else None
            page = await self._client.request(
                "GET", "/api/v0/equity/history/orders", params=params
            ) or {}
            for item in page.get("items") or []:
                if str(item.get("id")) == str(broker_order_id):
                    return item
            cursor = page.get("nextPagePath")
            if not cursor:
                break
        return None


__all__ = [
    "DEMO_BASE_URL",
    "LIVE_BASE_URL",
    "OPTIONAL_CONFIG",
    "REQUIRED_CONFIG",
    "Trading212Broker",
    "Trading212Client",
    "Trading212Error",
]
