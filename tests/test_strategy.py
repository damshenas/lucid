"""M10: strategy discovery, registry upsert, and config-schema integration."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.configs import ConfigService, load_default_config
from src.modules.strategy import StrategyRegistryService, discover_strategies, seed_missing_strategies


def test_discover_builtins() -> None:
    loaded = {s.name: s for s in discover_strategies("strategies")}
    assert "trend_follow" in loaded
    assert loaded["trend_follow"].direction == "buy"
    assert loaded["trend_follow"].is_builtin is True
    assert "trailing_stop" in loaded
    assert loaded["trailing_stop"].direction == "sell"


def test_seed_missing_strategies_fills_empty_mount_without_overwriting(tmp_path: Path) -> None:
    source = tmp_path / "builtin"
    target = tmp_path / "mounted"
    (source / "buy").mkdir(parents=True)
    (source / "buy" / "a.py").write_text("STRATEGY_NAME='a'\n")
    (target / "buy").mkdir(parents=True)
    (target / "buy" / "a.py").write_text("STRATEGY_NAME='a-customized'\n")

    seeded = seed_missing_strategies(source, target)

    assert seeded == []  # already present -> never overwritten
    assert "customized" in (target / "buy" / "a.py").read_text()


def test_seed_missing_strategies_noop_when_same_path(tmp_path: Path) -> None:
    assert seed_missing_strategies(tmp_path, tmp_path) == []


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


async def test_scan_removes_stale_entry_after_rename(tmp_path: Path, session: AsyncSession) -> None:
    """Renaming a strategy's STRATEGY_NAME must not leave the old name listed
    alongside the new one after the next scan."""
    (tmp_path / "buy").mkdir()
    strat_path = tmp_path / "buy" / "renamable.py"
    strat_path.write_text(
        "STRATEGY_NAME='old_name'\n"
        "STRATEGY_VERSION='1'\n"
        "CONFIG_SCHEMA={}\n"
        "async def run(context): return None\n"
    )

    registry = StrategyRegistryService(session, str(tmp_path))
    rows = await registry.scan()
    assert {r.name for r in rows} == {"old_name"}

    strat_path.write_text(
        "STRATEGY_NAME='new_name'\n"
        "STRATEGY_VERSION='1'\n"
        "CONFIG_SCHEMA={}\n"
        "async def run(context): return None\n"
    )
    rows2 = await registry.scan()
    names = {r.name for r in rows2}
    assert names == {"new_name"}
    assert "old_name" not in {r.name for r in await registry.list()}


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


async def test_all_extra_sections_includes_every_strategy_regardless_of_active(
    session: AsyncSession,
) -> None:
    """Settings must be able to show a tab per available strategy, not only whichever
    one happens to be active (that used to hide trend_follow entirely when no buy
    strategy was active yet)."""
    registry = StrategyRegistryService(session, "strategies")
    await registry.scan()

    extra = registry.all_extra_sections()

    assert "strategy.trend_follow" in extra
    assert "rsi_max" in extra["strategy.trend_follow"]
    assert "strategy.trailing_stop" in extra
    assert "atr_multiplier" in extra["strategy.trailing_stop"]
