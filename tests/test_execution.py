"""M6: execution pipeline (buy/sell, dedup lock, partial sell)."""

from __future__ import annotations

import asyncio

from src.modules.broker import PaperBroker
from src.modules.bus import BuySignalEvent, EventBus, OrderRejectedEvent, SellSignalEvent
from src.modules.db.connection import Database
from src.modules.db.models.base import PositionStatus
from src.modules.db.repositories.order import OrderRepository
from src.modules.db.repositories.position import PositionRepository
from src.modules.db.repositories.signal import SignalRepository
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


async def test_buy_records_acted_signal(db: Database) -> None:
    """Regression test: handle_buy previously never called SignalService at all, so
    GET /api/v1/signals stayed empty forever even after a strategy successfully
    bought. It must now store a Signal row and mark it acted."""
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.handle_buy(
        BuySignalEvent(ticker="AAPL", user_id=uid, source="trend_follow", reasoning="uptrend")
    )

    async with db.session() as s:
        signals = await SignalRepository(s).list_by_user(uid)
    assert len(signals) == 1
    assert signals[0].status == "acted"
    assert signals[0].source == "trend_follow"
    assert signals[0].acted_at is not None


async def test_buy_blocked_signal_when_position_already_open(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    async with db.transaction() as s:
        await PositionRepository(s).create(
            user_id=uid,
            ticker="AAPL",
            asset_class="equity",
            quantity=5.0,
            avg_price=90.0,
            status=PositionStatus.open.value,
        )

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="trend_follow"))

    async with db.session() as s:
        signals = await SignalRepository(s).list_by_user(uid)
    assert len(signals) == 1
    assert signals[0].status == "blocked"
    assert "position already open" in signals[0].reasoning


async def test_sell_records_acted_signal(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))
    await engine.handle_sell(SellSignalEvent(ticker="AAPL", user_id=uid, source="trailing_stop"))

    async with db.session() as s:
        signals = await SignalRepository(s).list_by_user(uid)
    sell_signals = [s for s in signals if s.direction == "sell"]
    assert len(sell_signals) == 1
    assert sell_signals[0].status == "acted"


async def test_sell_without_position_records_blocked_signal(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    engine = _engine(db, broker)

    await engine.handle_sell(SellSignalEvent(ticker="TSLA", user_id=uid, source="trailing_stop"))

    async with db.session() as s:
        signals = await SignalRepository(s).list_by_user(uid)
    assert len(signals) == 1
    assert signals[0].status == "blocked"
    assert "no open position" in signals[0].reasoning
