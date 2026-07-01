"""M4: event bus isolation and TTL cache behavior."""

from __future__ import annotations

import asyncio

from src.modules.bus import BuySignalEvent, EventBus, SellSignalEvent
from src.modules.cache import TTLCache


async def test_publish_calls_all_handlers() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def a(event: BuySignalEvent) -> None:
        seen.append(f"a:{event.ticker}")

    def b(event: BuySignalEvent) -> None:
        seen.append(f"b:{event.ticker}")

    bus.subscribe(BuySignalEvent, a)
    bus.subscribe(BuySignalEvent, b)
    await bus.publish(BuySignalEvent(ticker="AAPL", user_id=1, source="test"))

    assert sorted(seen) == ["a:AAPL", "b:AAPL"]


async def test_failing_handler_isolated() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def boom(event: BuySignalEvent) -> None:
        raise RuntimeError("kaboom")

    async def ok(event: BuySignalEvent) -> None:
        seen.append("ok")

    bus.subscribe(BuySignalEvent, boom)
    bus.subscribe(BuySignalEvent, ok)
    await bus.publish(BuySignalEvent(ticker="X", user_id=1, source="t"))

    assert seen == ["ok"]


async def test_only_matching_type_dispatched() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(BuySignalEvent, lambda e: seen.append("buy"))
    await bus.publish(SellSignalEvent(ticker="X", user_id=1, source="t"))
    assert seen == []


def test_ttl_cache_expiry() -> None:
    cache = TTLCache(default_ttl_seconds=100)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    assert "k" in cache

    cache.set("k2", "v2", ttl=-1)  # already expired
    assert cache.get("k2") is None
    assert "k2" not in cache


def test_ttl_cache_add_if_absent() -> None:
    cache = TTLCache()
    assert cache.add_if_absent("dedup:AAPL") is True
    assert cache.add_if_absent("dedup:AAPL") is False


def test_ttl_cache_max_entries_eviction() -> None:
    cache = TTLCache(max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert len(cache) == 2
    assert cache.get("a") is None  # oldest evicted


def test_event_loop_available() -> None:
    # sanity: asyncio import used above
    assert asyncio.get_event_loop_policy() is not None
