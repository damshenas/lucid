"""M5: paper broker fills, Trading212 client (mocked), and registry resolution."""

from __future__ import annotations

import httpx
import pytest

from src.modules.broker import BrokerNotRegisteredError, BrokerRegistry, PaperBroker
from src.modules.broker.base import Broker
from src.modules.com.trading212 import Trading212Broker, Trading212Client, Trading212Error


async def test_paper_broker_buy_then_sell() -> None:
    broker = PaperBroker(starting_cash=10_000.0)
    broker.set_price("AAPL", 100.0)

    buy = await broker.place_market_order("AAPL", 10)
    assert buy.status == "filled"
    assert buy.paper is True

    positions = await broker.get_positions()
    assert len(positions) == 1 and positions[0].quantity == 10

    sell = await broker.place_market_order("AAPL", -10)
    assert sell.status == "filled"
    assert await broker.get_positions() == []


async def test_paper_broker_sell_without_position_rejected() -> None:
    broker = PaperBroker()
    result = await broker.place_market_order("TSLA", -5)
    assert result.status == "rejected"


async def test_registry_paper_mode_returns_paper() -> None:
    registry = BrokerRegistry()
    broker = registry.resolve(broker_name="trading212", asset_class="equity", paper_mode=True)
    assert isinstance(broker, PaperBroker)


async def test_registry_resolves_per_asset_class() -> None:
    registry = BrokerRegistry()

    class EquityBroker(PaperBroker):
        name = "equitybroker"

    class CryptoBroker(PaperBroker):
        name = "cryptobroker"

    registry.register("mybroker", "equity", lambda **kw: EquityBroker())
    registry.register("mybroker", "crypto", lambda **kw: CryptoBroker())

    equity = registry.resolve(broker_name="mybroker", asset_class="equity")
    crypto = registry.resolve(broker_name="mybroker", asset_class="crypto")
    assert equity.name == "equitybroker"
    assert crypto.name == "cryptobroker"


async def test_registry_unknown_raises() -> None:
    registry = BrokerRegistry()
    with pytest.raises(BrokerNotRegisteredError):
        registry.resolve(broker_name="nope", asset_class="equity")


def _mock_client(handler) -> Trading212Client:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(base_url="https://api.t212.test", transport=transport)
    return Trading212Client("key", "https://api.t212.test", client=http, retry_attempts=2)


async def test_trading212_place_order_and_positions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/orders/market"):
            return httpx.Response(200, json={"id": 123, "status": "FILLED", "fillPrice": 101.5})
        if request.url.path.endswith("/portfolio"):
            return httpx.Response(200, json=[{"ticker": "AAPL", "quantity": 3, "averagePrice": 100}])
        if request.url.path.endswith("/account/cash"):
            return httpx.Response(200, json={"free": 500.0, "total": 800.0})
        return httpx.Response(404)

    client = _mock_client(handler)
    broker = Trading212Broker(client)

    order = await broker.place_market_order("AAPL", 3)
    assert order.status == "filled"
    assert order.broker_order_id == "123"
    assert order.avg_price == 101.5

    positions = await broker.get_positions()
    assert positions[0].ticker == "AAPL"

    summary = await broker.get_account_summary()
    assert summary.cash == 500.0

    await client.aclose()


async def test_trading212_retries_then_fails() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    client = _mock_client(handler)
    with pytest.raises(Trading212Error):
        await client.request("GET", "/api/v0/equity/portfolio")
    assert calls["n"] == 2  # retry_attempts
    await client.aclose()
