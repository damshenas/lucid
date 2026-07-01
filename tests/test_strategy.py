"""M10: strategy discovery, registry upsert, and config-schema integration."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.configs import ConfigService, load_default_config
from src.modules.strategy import StrategyRegistryService, discover_strategies


def test_discover_builtins() -> None:
    loaded = {s.name: s for s in discover_strategies("strategies")}
    assert "trend_follow" in loaded
    assert loaded["trend_follow"].direction == "buy"
    assert loaded["trend_follow"].is_builtin is True
    assert "trailing_stop" in loaded
    assert loaded["trailing_stop"].direction == "sell"


async def test_scan_upserts_registry(session: AsyncSession) -> None:
    registry = StrategyRegistryService(session, "strategies")
    rows = await registry.scan()
    names = {r.name: r for r in rows}
    assert "trend_follow" in names
    assert names["trend_follow"].direction == "buy"
    assert names["trailing_stop"].is_builtin is True

    # idempotent
    rows2 = await registry.scan()
    assert len(rows2) == len(rows)


async def test_active_strategy_resolution(session: AsyncSession) -> None:
    registry = StrategyRegistryService(session, "strategies")
    await registry.scan()
    config_values = {"strategy": {"active_buy_strategy": "trend_follow"}}
    active = registry.get_active(config_values, "buy")
    assert active is not None and active.name == "trend_follow"
    assert registry.get_active({"strategy": {}}, "buy") is None


async def test_compile_schema_includes_active_strategy(session: AsyncSession) -> None:
    defaults = load_default_config("src/conf/default.yml")
    svc = ConfigService(session, defaults)
    registry = StrategyRegistryService(session, "strategies")
    await registry.scan()

    config_values = await svc.compile_values(user_id=1)
    config_values.setdefault("strategy", {})["active_buy_strategy"] = "trend_follow"

    extra = registry.active_extra_sections(config_values)
    schema = await svc.compile_schema(user_id=1, extra_sections=extra)

    assert "strategy.trend_follow" in schema
    assert "rsi_max" in schema["strategy.trend_follow"]
    # default active_sell_strategy is trailing_stop
    assert "strategy.trailing_stop" in schema
