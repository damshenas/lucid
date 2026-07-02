"""M6: execution pipeline (buy/sell, dedup lock, partial sell)."""

from __future__ import annotations

import asyncio

from src.modules.broker import PaperBroker
from src.modules.bus import BuySignalEvent, EventBus, OrderRejectedEvent, SellSignalEvent
from src.modules.db.connection import Database
from src.modules.db.repositories.order import OrderRepository
from src.modules.db.repositories.position import PositionRepository
from src.modules.db.repositories.user import UserRepository
from src.modules.execution import ExecutionEngine


async def _make_user(db: Database) -> int:
    async with db.transaction() as s:
        user = await UserRepository(s).create(username="trader", password_hash="x", role="trader")
        return user.id


def _engine(db: Database, broker: PaperBroker, *, bus=None) -> ExecutionEngine:
    async def resolve(_uid: int, _ac: str) -> PaperBroker:
        return broker

    async def quote(_ticker: str) -> float:
        return 100.0

    async def config(_uid: int, _ac: str | None) -> dict:
        return {
            "execution": {"quantity_mode": "fixed_usd", "fixed_usd": 1000.0},
        }

    return ExecutionEngine(
        db=db, broker_resolver=resolve, quote_provider=quote, config_provider=config, bus=bus
    )


async def test_buy_creates_position_and_order(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="test"))

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert len(positions) == 1
    assert positions[0].quantity == 10.0  # 1000 usd / 100 price
    assert len(orders) == 1 and orders[0].side == "buy"


async def test_duplicate_buy_skipped_when_position_open(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))
    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert len(positions) == 1
    assert len(orders) == 1


async def test_concurrent_buys_deduped_by_lock(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    event = BuySignalEvent(ticker="AAPL", user_id=uid, source="t")
    await asyncio.gather(engine.handle_buy(event), engine.handle_buy(event))

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert len(positions) == 1
    assert len([o for o in orders if o.side == "buy"]) == 1


async def test_partial_then_full_sell(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))

    # sell half
    await engine.handle_sell(
        SellSignalEvent(ticker="AAPL", user_id=uid, source="t", quantity_pct=50.0)
    )
    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
    assert len(positions) == 1 and positions[0].quantity == 5.0

    # sell the rest (full)
    await engine.handle_sell(SellSignalEvent(ticker="AAPL", user_id=uid, source="t"))
    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert positions == []
    assert len([o for o in orders if o.side == "sell"]) == 2


async def test_sell_without_position_rejected(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()

    bus = EventBus()
    rejects: list[OrderRejectedEvent] = []
    bus.subscribe(OrderRejectedEvent, lambda e: rejects.append(e))
    engine = _engine(db, broker, bus=bus)

    await engine.handle_sell(SellSignalEvent(ticker="TSLA", user_id=uid, source="t"))
    assert rejects and rejects[0].reason == "no open position"
