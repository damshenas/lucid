"""M13: API integration — health, first-run setup, auth, settings, strategies."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.context import AppContext
from src.api.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    ctx = AppContext.build(database_url="sqlite+aiosqlite:///:memory:")
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
        json={"username": "view1", "password": "viewerpw"},
    )
    assert created.status_code == 201

    viewer_token = client.post(
        "/api/v1/auth/login", json={"username": "view1", "password": "viewerpw"}
    ).json()["access_token"]

    resp = client.post(
        "/api/v1/settings",
        headers=_auth(viewer_token),
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
        json={"key": "trading212_api_key", "value": "SYSTEM_KEY"},
    )
    assert set_resp.status_code == 204

    catalog2 = client.get("/api/v1/credentials/system", headers=_auth(admin_token)).json()
    configured = {row["key"]: row["configured"] for row in catalog2}
    assert configured["trading212_api_key"] is True

    # traders cannot manage system credentials
    assert (
        client.get("/api/v1/credentials/system", headers=_auth(trader_token)).status_code == 403
    )
    assert (
        client.post(
            "/api/v1/credentials/system",
            headers=_auth(trader_token),
            json={"key": "trading212_api_key", "value": "x"},
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
        json={"key": "trading212_api_key", "value": "USER_KEY"},
    )
    assert set_resp.status_code == 204

    mine2 = client.get("/api/v1/credentials/mine", headers=_auth(trader_token)).json()
    configured = {row["key"]: row["configured"] for row in mine2["credentials"]}
    assert configured["trading212_api_key"] is True

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

    # viewers/admins (no edit_own_strategies) cannot mutate the watchlist
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
    assert add.json() == {"ticker": "AMZN", "asset_class": "equity", "enabled": True}

    listing = client.get("/api/v1/prices/watchlist", headers=_auth(trader_token)).json()
    assert listing == [{"ticker": "AMZN", "asset_class": "equity", "enabled": True, "has_bars": False}]

    disable = client.patch(
        "/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token), json={"enabled": False}
    )
    assert disable.status_code == 200
    assert disable.json()["enabled"] is False

    missing = client.patch(
        "/api/v1/prices/watchlist/NOPE", headers=_auth(trader_token), json={"enabled": True}
    )
    assert missing.status_code == 404

    remove = client.delete("/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token))
    assert remove.status_code == 204
    assert client.get("/api/v1/prices/watchlist", headers=_auth(trader_token)).json() == []
    assert client.delete("/api/v1/prices/watchlist/AMZN", headers=_auth(trader_token)).status_code == 404


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
