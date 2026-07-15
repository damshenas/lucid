"""M3: layered config resolution, schema compilation, and the secrets rule."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.configs import (
    ConfigError,
    ConfigPermissionError,
    ConfigService,
    flatten,
    is_secret_key,
    load_default_config,
    unflatten,
)

_DEFAULTS = {
    "execution": {"fixed_usd": 100.0, "quantity_mode": "fixed_usd"},
    "git_sync": {"enabled": False},
}


def test_flatten_unflatten_round_trip() -> None:
    flat = flatten(_DEFAULTS)
    assert flat["execution.fixed_usd"] == 100.0
    assert unflatten(flat) == _DEFAULTS


def test_is_secret_key() -> None:
    assert is_secret_key("trading212.api_key")
    assert is_secret_key("telegram_token")
    assert is_secret_key("db.password")
    assert not is_secret_key("execution.fixed_usd")


def test_load_default_yml_ok() -> None:
    data = load_default_config("src/conf/default.yml")
    assert data["execution"]["fixed_usd"] == 100.0


async def test_resolution_order(session: AsyncSession) -> None:
    svc = ConfigService(session, _DEFAULTS)
    key = "execution.fixed_usd"
    ac = "equity"

    # default
    assert await svc.resolve(key, user_id=1, asset_class=ac) == 100.0

    # asset-class layer
    await svc.set_value(key, 200.0, role="admin", user_id=None, asset_class=ac)
    assert await svc.resolve(key, user_id=1, asset_class=ac) == 200.0

    # global layer beats asset-class
    await svc.set_value(key, 300.0, role="admin", user_id=None, asset_class=None)
    assert await svc.resolve(key, user_id=1, asset_class=ac) == 300.0

    # per-user beats global
    await svc.set_value(key, 400.0, role="admin", user_id=1, asset_class=None)
    assert await svc.resolve(key, user_id=1, asset_class=ac) == 400.0

    # per-user + asset-class is most specific
    await svc.set_value(key, 500.0, role="admin", user_id=1, asset_class=ac)
    assert await svc.resolve(key, user_id=1, asset_class=ac) == 500.0

    # a different user is unaffected -> sees global
    assert await svc.resolve(key, user_id=2, asset_class=ac) == 300.0


async def test_set_secret_rejected(session: AsyncSession) -> None:
    svc = ConfigService(session, _DEFAULTS)
    with pytest.raises(ConfigError):
        await svc.set_value("trading212.api_key", "SECRET", role="admin", user_id=1)


async def test_set_value_requires_permission(session: AsyncSession) -> None:
    svc = ConfigService(session, _DEFAULTS)
    with pytest.raises(ConfigPermissionError):
        await svc.set_value("execution.fixed_usd", 1.0, role="analyst", user_id=1)
    with pytest.raises(ConfigPermissionError):
        await svc.set_value("execution.fixed_usd", 1.0, role="trader", user_id=1)
    # admin may write general sections (globally) *and* strategy.* (the system
    # default); trader/analyst may additionally write strategy.* for themselves only
    # (both roles carry edit_own_strategies).
    await svc.set_value("execution.fixed_usd", 1.0, role="admin", user_id=1)
    await svc.set_value("strategy.active_buy_strategy", "trend_follow", role="admin", user_id=None)
    await svc.set_value("strategy.active_buy_strategy", "trend_follow", role="trader", user_id=1)
    await svc.set_value("strategy.active_buy_strategy", "trend_follow", role="analyst", user_id=1)


async def test_compile_schema_from_model(session: AsyncSession) -> None:
    svc = ConfigService(session, load_default_config("src/conf/default.yml"))
    schema = await svc.compile_schema(user_id=1, asset_class="equity")
    assert "execution" in schema
    assert schema["execution"]["fixed_usd"]["value"] == 100.0


async def test_compile_schema_changes_with_active_strategy(session: AsyncSession) -> None:
    svc = ConfigService(session, load_default_config("src/conf/default.yml"))

    schema_a = await svc.compile_schema(
        user_id=1,
        extra_sections={"buy_strategy": {"rsi_threshold": {"type": "float", "default": 30.0}}},
    )
    schema_b = await svc.compile_schema(
        user_id=1,
        extra_sections={"buy_strategy": {"lookback_days": {"type": "int", "default": 20}}},
    )
    assert "rsi_threshold" in schema_a["buy_strategy"]
    assert "rsi_threshold" not in schema_b["buy_strategy"]
    assert "lookback_days" in schema_b["buy_strategy"]
