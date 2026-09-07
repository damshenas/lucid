"""M6: execution pipeline (buy/sell, dedup lock, partial sell)."""

from __future__ import annotations

import asyncio

import pytest

from src.modules.broker import PaperBroker
from src.modules.broker.base import AccountSummary, Broker, BrokerPosition, OrderResult
from src.modules.bus import (
    BuySignalEvent,
    EventBus,
    OrderFilledEvent,
    OrderRejectedEvent,
    SellSignalEvent,
)
from src.modules.db.connection import Database
from src.modules.db.models.base import OrderStatus, PositionStatus
from src.modules.db.repositories.order import OrderRepository
from src.modules.db.repositories.position import PositionRepository
from src.modules.db.repositories.signal import SignalRepository
from src.modules.db.repositories.user import UserRepository
from src.modules.execution import ExecutionEngine, ManualOrderError


class _PendingThenSettleBroker(Broker):
    """Test double: every order is placed as 'pending' and only resolves to a final
    status once ``settle(broker_order_id, status, avg_price)`` is called — models a
    real broker (e.g. Trading212) that doesn't confirm a fill synchronously."""

    name = "pending-test"

    def __init__(self) -> None:
        self._seq = 0
        self._results: dict[str, OrderResult] = {}

    async def place_market_order(self, ticker: str, quantity: float, *, asset_class: str = "equity"):
        self._seq += 1
        order_id = f"pending-{self._seq}"
        result = OrderResult(ticker=ticker, quantity=quantity, status="pending", broker_order_id=order_id)
        self._results[order_id] = result
        return result

    def settle(self, broker_order_id: str, status: str, avg_price: float | None = None) -> None:
        prior = self._results[broker_order_id]
        self._results[broker_order_id] = OrderResult(
            ticker=prior.ticker,
            quantity=prior.quantity,
            status=status,
            broker_order_id=broker_order_id,
            avg_price=avg_price,
        )

    async def get_order_status(self, broker_order_id: str) -> OrderResult:
        return self._results[broker_order_id]

    async def get_positions(self) -> list[BrokerPosition]:
        return []

    async def get_account_summary(self) -> AccountSummary:
        return AccountSummary(cash=100_000.0, equity=100_000.0)

    async def cancel_order(self, broker_order_id: str) -> bool:
        return False


async def _make_user(db: Database) -> int:
    async with db.transaction() as s:
        user = await UserRepository(s).create(username="trader", password_hash="x", role="trader")
        return user.id


def _engine(
    db: Database, broker: PaperBroker, *, bus=None, dedup_window_seconds: int = 300
) -> ExecutionEngine:
    async def resolve(_uid: int, _ac: str) -> PaperBroker:
        return broker

    async def quote(_ticker: str) -> float:
        return 100.0

    async def config(_uid: int, _ac: str | None) -> dict:
        return {
            "execution": {
                "quantity_mode": "fixed_usd",
                "fixed_usd": 1000.0,
                "dedup_window_seconds": dedup_window_seconds,
            },
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


async def test_manual_buy_opens_position_and_records_manual_signal(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    order = await engine.place_manual_order(
        user_id=uid, ticker="AAPL", side="buy", quantity=3.0, asset_class="equity"
    )
    assert order["side"] == "buy"
    assert order["quantity"] == 3.0
    assert order["status"] == "filled"

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        signals = await SignalRepository(s).list_by_user(uid)
    assert len(positions) == 1 and positions[0].quantity == 3.0
    assert len(signals) == 1
    assert signals[0].source == "manual"
    assert signals[0].status == "acted"


async def test_manual_buy_increases_existing_position_with_weighted_avg(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.place_manual_order(user_id=uid, ticker="AAPL", side="buy", quantity=10.0)
    broker.set_price("AAPL", 200.0)
    await engine.place_manual_order(user_id=uid, ticker="AAPL", side="buy", quantity=10.0)

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
    assert len(positions) == 1
    assert positions[0].quantity == 20.0
    assert positions[0].avg_price == 150.0


async def test_manual_sell_without_position_raises(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    engine = _engine(db, broker)

    with pytest.raises(ManualOrderError, match="no open position"):
        await engine.place_manual_order(user_id=uid, ticker="TSLA", side="sell", quantity=1.0)


async def test_manual_sell_more_than_held_raises(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.place_manual_order(user_id=uid, ticker="AAPL", side="buy", quantity=5.0)

    with pytest.raises(ManualOrderError, match="only 5.0 held"):
        await engine.place_manual_order(user_id=uid, ticker="AAPL", side="sell", quantity=10.0)


async def test_manual_sell_partial_reduces_position(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.place_manual_order(user_id=uid, ticker="AAPL", side="buy", quantity=10.0)
    await engine.place_manual_order(user_id=uid, ticker="AAPL", side="sell", quantity=4.0)

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert len(positions) == 1 and positions[0].quantity == 6.0
    assert len([o for o in orders if o.side == "sell"]) == 1


async def test_buy_after_full_sell_reopens_same_ticker(db: Database) -> None:
    """Regression test for bugs.md finding 1: a closed position row used to
    permanently block re-buying the same ticker (uq_position_user_ticker applied
    across all statuses, not just open)."""
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker, dedup_window_seconds=0)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))
    await engine.handle_sell(SellSignalEvent(ticker="AAPL", user_id=uid, source="t"))
    async with db.session() as s:
        assert await PositionRepository(s).list_open(uid) == []

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert len(positions) == 1 and positions[0].status == PositionStatus.open.value
    assert len([o for o in orders if o.side == "buy"]) == 2


async def test_same_ticker_can_be_open_in_two_asset_classes(db: Database) -> None:
    """Regression test for bugs.md finding 5: position identity must include
    asset_class, not just (user_id, ticker)."""
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("BTCUSD", 100.0)
    engine = _engine(db, broker, dedup_window_seconds=0)

    await engine.handle_buy(
        BuySignalEvent(ticker="BTCUSD", user_id=uid, source="t", asset_class="crypto")
    )
    await engine.handle_buy(
        BuySignalEvent(ticker="BTCUSD", user_id=uid, source="t", asset_class="fx")
    )

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
    assert {p.asset_class for p in positions} == {"crypto", "fx"}
    assert len(positions) == 2



async def test_manual_and_strategy_orders_share_the_same_ticker_lock(db: Database) -> None:
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await asyncio.gather(
        engine.place_manual_order(user_id=uid, ticker="AAPL", side="buy", quantity=5.0),
        engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="trend_follow")),
    )

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
    # Only one of the two buys should have won (an open position already existed for
    # whichever ran second), never a duplicate/racing position row.
    assert len(positions) == 1


async def test_sell_with_profit_tier_marks_position_tier_taken(db: Database) -> None:
    """Regression: SellSignalEvent.profit_tier must flip Position.profit_tier{N}_taken
    so a tiered sell strategy (trailing_stop) never re-fires the same tier."""
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))
    await engine.handle_sell(
        SellSignalEvent(ticker="AAPL", user_id=uid, source="trailing_stop", quantity_pct=33.0, profit_tier=1)
    )

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
    assert len(positions) == 1
    assert positions[0].profit_tier1_taken is True
    assert positions[0].profit_tier2_taken is False

    await engine.handle_sell(
        SellSignalEvent(ticker="AAPL", user_id=uid, source="trailing_stop", quantity_pct=33.0, profit_tier=2)
    )
    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
    assert positions[0].profit_tier1_taken is True
    assert positions[0].profit_tier2_taken is True


async def test_concurrent_identical_tier_events_only_sell_once(db: Database) -> None:
    """Regression test for bugs.md finding 7: two overlapping strategy evaluations
    (e.g. the scheduler and an activation-triggered background run) can both decide
    to fire the same profit tier before either commits. The second must be rejected
    once it sees the tier already marked, not sell the configured percentage twice."""
    uid = await _make_user(db)
    broker = PaperBroker()
    broker.set_price("AAPL", 100.0)
    engine = _engine(db, broker)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))
    event = SellSignalEvent(
        ticker="AAPL", user_id=uid, source="trailing_stop", quantity_pct=33.0, profit_tier=1
    )
    await asyncio.gather(engine.handle_sell(event), engine.handle_sell(event))

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    sell_orders = [o for o in orders if o.side == "sell"]
    assert len(sell_orders) == 1
    assert positions[0].quantity == pytest.approx(10.0 - (10.0 * 0.33))
    assert positions[0].profit_tier1_taken is True


async def test_pending_buy_does_not_open_position(db: Database) -> None:
    """Regression test for bugs.md finding 2: a broker order reported as anything
    other than 'filled' must never open/mutate a position — it must be persisted as
    pending until reconciled."""
    uid = await _make_user(db)
    broker = _PendingThenSettleBroker()
    bus = EventBus()
    fills: list[OrderFilledEvent] = []
    bus.subscribe(OrderFilledEvent, lambda e: fills.append(e))
    engine = _engine(db, broker, bus=bus)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert positions == []
    assert len(orders) == 1
    assert orders[0].status == OrderStatus.pending.value
    assert fills == []


async def test_pending_sell_does_not_reduce_position(db: Database) -> None:
    uid = await _make_user(db)
    broker = _PendingThenSettleBroker()
    engine = _engine(db, broker)

    async with db.transaction() as s:
        await PositionRepository(s).create(
            user_id=uid,
            ticker="AAPL",
            asset_class="equity",
            quantity=10.0,
            avg_price=100.0,
            status=PositionStatus.open.value,
            opened_at=None,
        )

    await engine.handle_sell(SellSignalEvent(ticker="AAPL", user_id=uid, source="t"))

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert len(positions) == 1 and positions[0].quantity == 10.0
    assert orders[0].status == OrderStatus.pending.value


async def test_reconcile_applies_fill_after_pending_buy(db: Database) -> None:
    uid = await _make_user(db)
    broker = _PendingThenSettleBroker()
    bus = EventBus()
    fills: list[OrderFilledEvent] = []
    bus.subscribe(OrderFilledEvent, lambda e: fills.append(e))
    engine = _engine(db, broker, bus=bus)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))
    async with db.session() as s:
        order = (await OrderRepository(s).list_by_user(uid))[0]
    broker.settle(order.broker_order_id, "filled", avg_price=105.0)

    await engine.reconcile_pending_orders()

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert len(positions) == 1
    assert positions[0].quantity == 10.0  # 1000 usd / 100 quote price used for sizing
    assert positions[0].avg_price == 105.0
    assert orders[0].status == OrderStatus.filled.value
    assert len(fills) == 1 and fills[0].price == 105.0


async def test_reconcile_marks_rejected_with_no_position_change(db: Database) -> None:
    uid = await _make_user(db)
    broker = _PendingThenSettleBroker()
    engine = _engine(db, broker)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))
    async with db.session() as s:
        order = (await OrderRepository(s).list_by_user(uid))[0]
    broker.settle(order.broker_order_id, "rejected")

    await engine.reconcile_pending_orders()

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert positions == []
    assert orders[0].status == OrderStatus.rejected.value


async def test_reconcile_leaves_still_pending_order_untouched(db: Database) -> None:
    uid = await _make_user(db)
    broker = _PendingThenSettleBroker()
    engine = _engine(db, broker)

    await engine.handle_buy(BuySignalEvent(ticker="AAPL", user_id=uid, source="t"))
    await engine.reconcile_pending_orders()

    async with db.session() as s:
        positions = await PositionRepository(s).list_open(uid)
        orders = await OrderRepository(s).list_by_user(uid)
    assert positions == []
    assert orders[0].status == OrderStatus.pending.value


