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

    schema = client.get("/api/v1/settings/schema", headers=_auth(token))
    assert schema.status_code == 200
    assert "execution" in schema.json()

    # built-in strategies were scanned at startup
    listing = client.get("/api/v1/strategies", headers=_auth(token)).json()
    names = {row["name"] for row in listing}
    assert {"trend_follow", "trailing_stop"} <= names

    assert client.get("/api/v1/positions", headers=_auth(token)).json() == []


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
