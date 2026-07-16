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


class Trading212Broker(Broker):
    name = "trading212"

    def __init__(self, client: Trading212Client, *, paper: bool = False) -> None:
        self._client = client
        self._paper = paper

    async def place_market_order(
        self, ticker: str, quantity: float, *, asset_class: str = AssetClass.equity.value
    ) -> OrderResult:
        payload = {"ticker": ticker, "quantity": quantity}
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
        data = await self._client.request("GET", "/api/v0/equity/portfolio") or []
        return [
            BrokerPosition(
                ticker=item["ticker"],
                quantity=float(item.get("quantity", 0.0)),
                avg_price=float(item.get("averagePrice", 0.0)),
                market_price=item.get("currentPrice"),
            )
            for item in data
        ]

    async def get_account_summary(self) -> AccountSummary:
        data = await self._client.request("GET", "/api/v0/equity/account/cash") or {}
        return AccountSummary(
            cash=float(data.get("free", 0.0)),
            equity=float(data.get("total", 0.0)),
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await self._client.request("DELETE", f"/api/v0/equity/orders/{broker_order_id}")
            return True
        except Trading212Error as exc:
            _logger.warning("cancel_order failed for %s: %s", broker_order_id, exc)
            return False


__all__ = [
    "DEMO_BASE_URL",
    "LIVE_BASE_URL",
    "OPTIONAL_CONFIG",
    "REQUIRED_CONFIG",
    "Trading212Broker",
    "Trading212Client",
    "Trading212Error",
]
