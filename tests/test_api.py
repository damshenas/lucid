"""M13: API integration — health, first-run setup, auth, settings, strategies."""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.context import AppContext
from src.api.main import create_app
from src.modules.broker import BrokerRegistry, PaperBroker
from src.modules.price import storage


def _mock_broker_registry() -> BrokerRegistry:
    """A broker registry that maps 'trading212' to a PaperBroker — no
    network calls, no credentials required.  Used in API integration tests
    that exercise the execution/position layer without hitting Trading212."""
    registry = BrokerRegistry()
    paper = PaperBroker()
    registry.register("trading212", "equity", lambda **kw: paper)
    return registry


@pytest.fixture
def client() -> Iterator[TestClient]:
    ctx = AppContext.build(
        database_url="sqlite+aiosqlite:///:memory:",
        broker_registry=_mock_broker_registry(),
    )
    app = create_app(ctx)
    with TestClient(app) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_live(client: TestClient) -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_health_ready(client: TestClient) -> None:
    assert client.get("/health/ready").status_code == 200


def test_setup_login_and_locked(client: TestClient) -> None:
    assert client.get("/api/v1/auth/status").json() == {"initialized": False}

    resp = client.post("/api/v1/auth/setup", json={"username": "root", "password": "password123"})
    assert resp.status_code == 201
    assert resp.json()["access_token"]

    assert client.get("/api/v1/auth/status").json() == {"initialized": True}

    # second setup is locked
    assert (
        client.post("/api/v1/auth/setup", json={"username": "x", "password": "password123"}).status_code
        == 409
    )

    login = client.post("/api/v1/auth/login", json={"username": "root", "password": "password123"})
    assert login.status_code == 200


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/positions").status_code == 401


def test_settings_schema_and_strategies(client: TestClient) -> None:
    token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]

    schema = client.get("/api/v1/settings/schema", headers=_auth(token)).json()
    assert "execution" in schema
    # Every discovered strategy shows up (not only the active one) — active_buy_strategy
    # is unset by default, but its config should still be browsable/activatable.
    assert "strategy.trend_follow" in schema
    assert "strategy.trailing_stop" in schema

    # built-in strategies were scanned at startup
    listing = client.get("/api/v1/strategies", headers=_auth(token)).json()
    names = {row["name"] for row in listing}
    assert {"trend_follow", "trailing_stop"} <= names

    assert client.get("/api/v1/positions", headers=_auth(token)).json() == []


def test_strategy_decisions_endpoint(client: TestClient) -> None:
    token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]

    # No decisions recorded yet (nothing has evaluated it) -> empty, not an error.
    resp = client.get("/api/v1/strategies/trend_follow/decisions", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []


def test_save_secret_rejected(client: TestClient) -> None:
    token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    resp = client.post(
        "/api/v1/settings",
        headers=_auth(token),
        json={"values": {"trading212.api_key": "SECRET"}},
    )
    assert resp.status_code == 400


def test_settings_write_requires_permission(client: TestClient) -> None:
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]

    created = client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "analyst1", "password": "analystpw"},
    )
    assert created.status_code == 201

    analyst_token = client.post(
        "/api/v1/auth/login", json={"username": "analyst1", "password": "analystpw"}
    ).json()["access_token"]

    resp = client.post(
        "/api/v1/settings",
        headers=_auth(analyst_token),
        json={"values": {"execution.fixed_usd": 50.0}},
    )
    assert resp.status_code == 403

    admin_resp = client.post(
        "/api/v1/settings",
        headers=_auth(admin_token),
        json={"values": {"execution.fixed_usd": 50.0}},
    )
    assert admin_resp.status_code == 200


def test_admin_sets_global_default_strategy_visible_to_trader(client: TestClient) -> None:
    """Regression: admin's writes must apply globally (not just to their own,
    trading-disabled account), so a trader picks up the admin-chosen default."""
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "trader3", "password": "traderpass", "role": "trader"},
    )
    trader_token = client.post(
        "/api/v1/auth/login", json={"username": "trader3", "password": "traderpass"}
    ).json()["access_token"]

    resp = client.post(
        "/api/v1/settings",
        headers=_auth(admin_token),
        json={"values": {"strategy.active_buy_strategy": "trend_follow"}},
    )
    assert resp.status_code == 200

    values = client.get("/api/v1/settings", headers=_auth(trader_token)).json()
    assert values["strategy"]["active_buy_strategy"] == "trend_follow"


def test_create_user_invalid_role_rejected(client: TestClient) -> None:
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    resp = client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "bob", "password": "somepassword", "role": "superadmin"},
    )
    assert resp.status_code == 422


def test_admin_user_crud(client: TestClient) -> None:
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    created = client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "bob", "password": "somepassword", "role": "analyst"},
    ).json()
    user_id = created["id"]

    # edit role
    resp = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=_auth(admin_token),
        json={"role": "trader"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "trader"

    # reset password forces must_change_password and lets the user log in with it
    resp = client.post(
        f"/api/v1/admin/users/{user_id}/reset-password",
        headers=_auth(admin_token),
        json={"new_password": "brandnewpw1"},
    )
    assert resp.status_code == 200
    login = client.post(
        "/api/v1/auth/login", json={"username": "bob", "password": "brandnewpw1"}
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True

    # deactivate blocks login
    resp = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=_auth(admin_token),
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    blocked = client.post(
        "/api/v1/auth/login", json={"username": "bob", "password": "brandnewpw1"}
    )
    assert blocked.status_code == 401

    # delete removes the row
    resp = client.delete(f"/api/v1/admin/users/{user_id}", headers=_auth(admin_token))
    assert resp.status_code == 204
    remaining = client.get("/api/v1/admin/users", headers=_auth(admin_token)).json()
    assert all(u["id"] != user_id for u in remaining)


def test_admin_cannot_delete_or_deactivate_last_admin(client: TestClient) -> None:
    setup = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()
    admin_token = setup["access_token"]
    admin_id = client.get("/api/v1/admin/users", headers=_auth(admin_token)).json()[0]["id"]

    resp = client.delete(f"/api/v1/admin/users/{admin_id}", headers=_auth(admin_token))
    assert resp.status_code == 409

    resp = client.patch(
        f"/api/v1/admin/users/{admin_id}",
        headers=_auth(admin_token),
        json={"is_active": False},
    )
    assert resp.status_code == 409


def test_manual_order_trader_only(client: TestClient) -> None:
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "trader1", "password": "traderpass", "role": "trader"},
    )
    client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "analyst1", "password": "analystpw", "role": "analyst"},
    )
    trader_token = client.post(
        "/api/v1/auth/login", json={"username": "trader1", "password": "traderpass"}
    ).json()["access_token"]
    analyst_token = client.post(
        "/api/v1/auth/login", json={"username": "analyst1", "password": "analystpw"}
    ).json()["access_token"]

    # analysts cannot place manual orders
    resp = client.post(
        "/api/v1/orders/manual",
        headers=_auth(analyst_token),
        json={"ticker": "AAPL", "side": "buy", "quantity": 2},
    )
    assert resp.status_code == 403

    # trader can
    resp = client.post(
        "/api/v1/orders/manual",
        headers=_auth(trader_token),
        json={"ticker": "AAPL", "side": "buy", "quantity": 2},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["side"] == "buy"
    assert body["quantity"] == 2

    orders = client.get("/api/v1/orders", headers=_auth(trader_token)).json()
    assert len(orders) == 1

    # selling more than held is rejected with 400
    resp = client.post(
        "/api/v1/orders/manual",
        headers=_auth(trader_token),
        json={"ticker": "AAPL", "side": "sell", "quantity": 999},
    )
    assert resp.status_code == 400


def test_sync_reflects_broker_positions_after_manual_order(client: TestClient) -> None:
    """After placing a manual order, POST /positions/sync must query the broker
    and keep positions that the broker reports (not close them).  Previously the
    code routed paper_mode=True to an ephemeral in-memory PaperBroker instead of
    the real Trading212 paper account, so the broker had no knowledge of the order
    and sync closed the local position."""
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "trader1", "password": "traderpass", "role": "trader"},
    )
    token = client.post(
        "/api/v1/auth/login", json={"username": "trader1", "password": "traderpass"}
    ).json()["access_token"]

    # Place a manual order — the mock broker fills it and tracks the position.
    resp = client.post(
        "/api/v1/orders/manual",
        headers=_auth(token),
        json={"ticker": "AMZN", "side": "buy", "quantity": 1},
    )
    assert resp.status_code == 201

    # Position is visible before sync.
    positions = client.get("/api/v1/positions", headers=_auth(token)).json()
    assert any(p["ticker"] == "AMZN" for p in positions)

    # Sync queries the broker; it reports AMZN so the position is updated, not closed.
    sync_resp = client.post("/api/v1/positions/sync", headers=_auth(token))
    assert sync_resp.status_code == 200
    assert sync_resp.json()["closed"] == 0

    # Position must still be open after the sync.
    positions_after = client.get("/api/v1/positions", headers=_auth(token)).json()
    assert any(p["ticker"] == "AMZN" for p in positions_after)


def test_admin_reports_permission_and_empty_state(client: TestClient) -> None:
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "trader1", "password": "traderpass", "role": "trader"},
    )
    trader_token = client.post(
        "/api/v1/auth/login", json={"username": "trader1", "password": "traderpass"}
    ).json()["access_token"]

    assert (
        client.get(
            "/api/v1/admin/reports/price-coverage", headers=_auth(trader_token)
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/admin/reports/fetch-activity", headers=_auth(trader_token)
        ).status_code
        == 403
    )

    coverage = client.get("/api/v1/admin/reports/price-coverage", headers=_auth(admin_token))
    assert coverage.status_code == 200
    assert coverage.json() == []

    activity = client.get("/api/v1/admin/reports/fetch-activity", headers=_auth(admin_token))
    assert activity.status_code == 200
    assert activity.json() == []


def test_admin_price_coverage_report_reflects_stored_bars(tmp_path) -> None:
    ctx = AppContext.build(database_url="sqlite+aiosqlite:///:memory:")
    ctx.settings.price.storage_path = str(tmp_path)
    app = create_app(ctx)
    with TestClient(app) as client:
        admin_token = client.post(
            "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
        ).json()["access_token"]

        df = pd.DataFrame(
            {"open": [1.0, 1.1], "high": [1.0, 1.1], "low": [1.0, 1.1], "close": [1.0, 1.1], "volume": [1.0, 1.0]},
            index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        )
        storage.write_bars(tmp_path, "AAPL", "1d", df)

        resp = client.get("/api/v1/admin/reports/price-coverage", headers=_auth(admin_token))
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["ticker"] == "AAPL"
        assert rows[0]["interval"] == "1d"
        assert rows[0]["bar_count"] == 2


def test_system_credentials_admin_only(client: TestClient) -> None:
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "trader1", "password": "traderpass", "role": "trader"},
    )
    trader_token = client.post(
        "/api/v1/auth/login", json={"username": "trader1", "password": "traderpass"}
    ).json()["access_token"]

    catalog = client.get("/api/v1/credentials/system", headers=_auth(admin_token))
    assert catalog.status_code == 200
    assert all(item["configured"] is False for item in catalog.json())

    set_resp = client.post(
        "/api/v1/credentials/system",
        headers=_auth(admin_token),
        json={"key": "trading212_key_id", "value": "SYSTEM_KEY"},
    )
    assert set_resp.status_code == 204

    catalog2 = client.get("/api/v1/credentials/system", headers=_auth(admin_token)).json()
    configured = {row["key"]: row["configured"] for row in catalog2}
    assert configured["trading212_key_id"] is True

    # traders cannot manage system credentials
    assert (
        client.get("/api/v1/credentials/system", headers=_auth(trader_token)).status_code == 403
    )
    assert (
        client.post(
            "/api/v1/credentials/system",
            headers=_auth(trader_token),
            json={"key": "trading212_key_id", "value": "x"},
        ).status_code
        == 403
    )

    # unknown keys are rejected
    bad = client.post(
        "/api/v1/credentials/system",
        headers=_auth(admin_token),
        json={"key": "not_a_real_key", "value": "x"},
    )
    assert bad.status_code == 400


def test_own_credentials_trader_only(client: TestClient) -> None:
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "trader2", "password": "traderpass", "role": "trader"},
    )
    trader_token = client.post(
        "/api/v1/auth/login", json={"username": "trader2", "password": "traderpass"}
    ).json()["access_token"]

    mine = client.get("/api/v1/credentials/mine", headers=_auth(trader_token))
    assert mine.status_code == 200
    assert mine.json()["use_default_credentials"] is False

    set_resp = client.post(
        "/api/v1/credentials/mine",
        headers=_auth(trader_token),
        json={"key": "trading212_key_id", "value": "USER_KEY"},
    )
    assert set_resp.status_code == 204

    mine2 = client.get("/api/v1/credentials/mine", headers=_auth(trader_token)).json()
    configured = {row["key"]: row["configured"] for row in mine2["credentials"]}
    assert configured["trading212_key_id"] is True

    toggle = client.patch(
        "/api/v1/credentials/mine/use-default",
        headers=_auth(trader_token),
        json={"use_default_credentials": True},
    )
    assert toggle.status_code == 204
    assert client.get("/api/v1/credentials/mine", headers=_auth(trader_token)).json()[
        "use_default_credentials"
    ] is True

    # admin (no edit_own_credentials permission) cannot use the "mine" routes
    assert client.get("/api/v1/credentials/mine", headers=_auth(admin_token)).status_code == 403


def test_price_watchlist_crud(client: TestClient) -> None:
    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]
    client.post(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        json={"username": "trader4", "password": "traderpass", "role": "trader"},
    )
    trader_token = client.post(
        "/api/v1/auth/login", json={"username": "trader4", "password": "traderpass"}
    ).json()["access_token"]

    assert client.get("/api/v1/prices/watchlist", headers=_auth(trader_token)).json() == []

    # admins (no edit_own_strategies) cannot mutate the watchlist
    assert (
        client.post(
            "/api/v1/prices/watchlist",
            headers=_auth(admin_token),
            json={"ticker": "amzn", "asset_class": "equity"},
        ).status_code
        == 403
    )

    add = client.post(
        "/api/v1/prices/watchlist",
        headers=_auth(trader_token),
        json={"ticker": "amzn", "asset_class": "equity"},
    )
    assert add.status_code == 201
    assert add.json() == {
        "ticker": "AMZN",
        "asset_class": "equity",
        "enabled": True,
        "poll_interval": "1h",  # default when not specified
        "region": "us",  # default when not specified
    }

    listing = client.get("/api/v1/prices/watchlist", headers=_auth(trader_token)).json()
    assert listing == [
        {
            "ticker": "AMZN",
            "asset_class": "equity",
            "enabled": True,
            "poll_interval": "1h",
            "region": "us",
            "has_bars": False,
            "on_watchlist": True,
        }
    ]

    set_minute = client.patch(
        "/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token), json={"poll_interval": "1m"}
    )
    assert set_minute.status_code == 200
    assert set_minute.json()["poll_interval"] == "1m"

    bad_interval = client.patch(
        "/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token), json={"poll_interval": "15m"}
    )
    assert bad_interval.status_code == 422

    disable = client.patch(
        "/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token), json={"enabled": False}
    )
    assert disable.status_code == 200
    assert disable.json()["enabled"] is False
    assert disable.json()["poll_interval"] == "1m"  # untouched by an enabled-only patch

    set_region = client.patch(
        "/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token), json={"region": "eu"}
    )
    assert set_region.status_code == 200
    assert set_region.json()["region"] == "eu"

    bad_region = client.patch(
        "/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token), json={"region": "apac"}
    )
    assert bad_region.status_code == 422

    missing = client.patch(
        "/api/v1/prices/watchlist/NOPE", headers=_auth(trader_token), json={"enabled": True}
    )
    assert missing.status_code == 404

    remove = client.delete("/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token))
    assert remove.status_code == 204
    assert client.get("/api/v1/prices/watchlist", headers=_auth(trader_token)).json() == []
    assert client.delete("/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token)).status_code == 404


def test_watchlist_disk_only_tickers_are_not_editable(tmp_path) -> None:
    """Regression: a ticker with stored bars but never actually POSTed to the
    watchlist (e.g. an ad-hoc backfill, or the migrate_legacy_prices script) used to
    be indistinguishable from a real entry in GET /watchlist's response — the
    Settings > Watchlist UI would let a user "toggle" it and then 404 on Save
    (PATCH/DELETE on a ticker never actually added). ``on_watchlist`` now marks which
    rows are real."""
    ctx = AppContext.build(database_url="sqlite+aiosqlite:///:memory:")
    ctx.settings.price.storage_path = str(tmp_path)
    app = create_app(ctx)
    with TestClient(app) as client:
        admin_token = client.post(
            "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
        ).json()["access_token"]
        client.post(
            "/api/v1/admin/users",
            headers=_auth(admin_token),
            json={"username": "trader5", "password": "traderpass", "role": "trader"},
        )
        trader_token = client.post(
            "/api/v1/auth/login", json={"username": "trader5", "password": "traderpass"}
        ).json()["access_token"]

        # A ticker with bars on disk but no price_watchlist row at all.
        df = pd.DataFrame(
            {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]},
            index=pd.to_datetime(["2024-01-01"]),
        )
        storage.write_bars(tmp_path, "GHOST", "1d", df)

        client.post(
            "/api/v1/prices/watchlist",
            headers=_auth(trader_token),
            json={"ticker": "amzn", "asset_class": "equity"},
        )

        listing = {
            row["ticker"]: row
            for row in client.get("/api/v1/prices/watchlist", headers=_auth(trader_token)).json()
        }
        assert listing["AMZN"]["on_watchlist"] is True
        assert listing["GHOST"]["on_watchlist"] is False

        # Same 404 as any other never-added ticker — a disk-only entry is never
        # editable until it's actually POSTed.
        assert (
            client.patch(
                "/api/v1/prices/watchlist/GHOST",
                headers=_auth(trader_token),
                json={"poll_interval": "1m"},
            ).status_code
            == 404
        )


def test_log_level_applied_live_unless_env_override(monkeypatch) -> None:
    import logging

    from src.modules.logger import set_level

    monkeypatch.delenv("LOG_LEVEL", raising=False)
    set_level("DEBUG")
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
    set_level("WARNING")
    assert logging.getLogger().getEffectiveLevel() == logging.WARNING


def test_settings_save_applies_log_level_live_unless_env_override(
    client: TestClient, monkeypatch
) -> None:
    import src.api.v1.settings as settings_module

    calls: list[str] = []
    monkeypatch.setattr(settings_module, "set_level", calls.append)

    admin_token = client.post(
        "/api/v1/auth/setup", json={"username": "root", "password": "password123"}
    ).json()["access_token"]

    monkeypatch.delenv("LOG_LEVEL", raising=False)
    resp = client.post(
        "/api/v1/settings",
        headers=_auth(admin_token),
        json={"values": {"logger.level": "DEBUG"}},
    )
    assert resp.status_code == 200
    assert calls == ["DEBUG"]

    # An ops-level LOG_LEVEL env var always wins — a Settings change has no live
    # effect (and never will, until the env var is unset) while it's present.
    monkeypatch.setenv("LOG_LEVEL", "info")
    client.post(
        "/api/v1/settings",
        headers=_auth(admin_token),
        json={"values": {"logger.level": "CRITICAL"}},
    )
    assert calls == ["DEBUG"]  # unchanged — second call was skipped
