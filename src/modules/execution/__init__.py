"""Execution pipeline: turn signals into broker orders.

This module makes no trading decisions — strategies decide, it executes. It:
- de-duplicates concurrent orders per ticker with an ``asyncio.Lock``
- skips buys when a position is already open
- sizes the order (``fixed_usd`` | ``pct_portfolio`` | ``half_kelly``)
- places the order via the resolved broker
- records the order/position and publishes fill/reject events
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from src.conf.schema import AssetClass
from src.modules.broker.base import Broker
from src.modules.bus import (
    BuySignalEvent,
    EventBus,
    OrderFilledEvent,
    OrderRejectedEvent,
    SellSignalEvent,
)
from src.modules.db.connection import Database
from src.modules.db.models.base import OrderSide, OrderStatus, PositionStatus, SignalStatus
from src.modules.db.repositories.order import OrderRepository
from src.modules.db.repositories.position import PositionRepository
from src.modules.db.repositories.signal import SignalRepository
from src.modules.logger import get_logger
from src.modules.signal import SignalService


from .sizing import compute_buy_quantity

BrokerResolver = Callable[[int, str], Awaitable[Broker] | Broker]
QuoteProvider = Callable[[str], Awaitable[float] | float]
ConfigProvider = Callable[[int, str | None], Awaitable[dict[str, Any]] | dict[str, Any]]

_logger = get_logger("execution")


class ManualOrderError(Exception):
    """Raised when a manual order can't be placed (rejected/insufficient position/etc.)."""


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


_ORDER_STATUS_VALUES = {s.value for s in OrderStatus}


def _normalize_order_status(status: str) -> str:
    """A broker-reported status that isn't one of Lucid's known ``OrderStatus``
    values fails closed to ``pending`` rather than being trusted as-is, so an
    unrecognized status still gets picked up by reconcile_pending_orders instead of
    being silently misrepresented."""
    return status if status in _ORDER_STATUS_VALUES else OrderStatus.pending.value


class ExecutionEngine:
    def __init__(
        self,
        *,
        db: Database,
        broker_resolver: BrokerResolver,
        quote_provider: QuoteProvider,
        config_provider: ConfigProvider,
        bus: EventBus | None = None,
    ) -> None:
        self._db = db
        self._resolve_broker = broker_resolver
        self._quote = quote_provider
        self._config = config_provider
        self._bus = bus
        self._locks: dict[tuple[int, str], asyncio.Lock] = {}

    def subscribe(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(BuySignalEvent, self.handle_buy)
        bus.subscribe(SellSignalEvent, self.handle_sell)

    def _lock(self, user_id: int, ticker: str, asset_class: str) -> asyncio.Lock:
        key = (user_id, ticker, asset_class)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def _publish(self, event: Any) -> None:
        if self._bus is not None:
            await self._bus.publish(event)

    async def _reject(self, ticker: str, user_id: int, side: str, reason: str) -> None:
        _logger.info("order rejected %s %s for user %s: %s", side, ticker, user_id, reason)
        await self._publish(OrderRejectedEvent(user_id=user_id, ticker=ticker, side=side, reason=reason))

    async def handle_buy(self, event: BuySignalEvent) -> None:
        async with self._lock(event.user_id, event.ticker, event.asset_class):
            config = await _maybe_await(self._config(event.user_id, event.asset_class))
            execution_cfg = config.get("execution", {})
            dedup_seconds = int(execution_cfg.get("dedup_window_seconds", 300))

            # Persist the signal first, in its own committed transaction, so it's
            # visible (GET /api/v1/signals, pages/StrategyDetail.tsx) even if
            # everything below fails or raises — previously nothing was ever
            # written here at all, so the Signals feed stayed empty forever.
            async with self._db.transaction() as session:
                signal_service = SignalService(session, dedup_window_seconds=dedup_seconds)
                if await signal_service.is_duplicate(event.user_id, event.ticker, "buy"):
                    return
                signal = await signal_service.store_from_event(event)
                signal_id = signal.id

            try:
                async with self._db.transaction() as session:
                    positions = PositionRepository(session)
                    orders = OrderRepository(session)
                    signal_service = SignalService(session)
                    signal = await SignalRepository(session).get_by_id(signal_id)

                    if (
                        await positions.get_open_by_ticker(event.user_id, event.ticker, event.asset_class)
                        is not None
                    ):
                        await signal_service.mark_blocked(signal, reason="position already open")
                        await self._reject(event.ticker, event.user_id, "buy", "position already open")
                        return

                    price = float(await _maybe_await(self._quote(event.ticker)))
                    if price <= 0:
                        await signal_service.mark_blocked(signal, reason="no price")
                        await self._reject(event.ticker, event.user_id, "buy", "no price")
                        return

                    broker = await _maybe_await(self._resolve_broker(event.user_id, event.asset_class))
                    summary = await broker.get_account_summary()
                    quantity = compute_buy_quantity(
                        mode=execution_cfg.get("quantity_mode", "fixed_usd"),
                        price=price,
                        config=execution_cfg,
                        portfolio_value=summary.equity,
                        confidence=event.confidence,
                    )
                    if quantity <= 0:
                        await signal_service.mark_blocked(signal, reason="zero quantity")
                        await self._reject(event.ticker, event.user_id, "buy", "zero quantity")
                        return

                    result = await broker.place_market_order(
                        event.ticker, quantity, asset_class=event.asset_class
                    )
                    if result.status == OrderStatus.rejected.value:
                        reason = result.reason or "broker rejected"
                        await signal_service.mark_blocked(signal, reason=reason)
                        await self._reject(event.ticker, event.user_id, "buy", reason)
                        return

                    if result.status != OrderStatus.filled.value:
                        # Broker accepted the order but hasn't confirmed a fill yet
                        # (e.g. "pending") — never mutate position state on anything
                        # short of a confirmed fill. Persisted as pending and finalized
                        # later by reconcile_pending_orders once the broker settles it.
                        await orders.create(
                            user_id=event.user_id,
                            ticker=event.ticker,
                            asset_class=event.asset_class,
                            side=OrderSide.buy.value,
                            quantity=quantity,
                            price=result.avg_price,
                            status=_normalize_order_status(result.status),
                            broker_order_id=result.broker_order_id,
                            paper=result.paper,
                        )
                        await signal_service.mark_acted(signal)
                        return

                    fill_price = result.avg_price or price
                    now = datetime.now(timezone.utc)
                    position = await positions.create(
                        user_id=event.user_id,
                        ticker=event.ticker,
                        asset_class=event.asset_class,
                        quantity=quantity,
                        avg_price=fill_price,
                        high_water_mark=fill_price,
                        status=PositionStatus.open.value,
                        opened_at=now,
                    )
                    await orders.create(
                        user_id=event.user_id,
                        ticker=event.ticker,
                        asset_class=event.asset_class,
                        side=OrderSide.buy.value,
                        quantity=quantity,
                        price=fill_price,
                        status=OrderStatus.filled.value,
                        broker_order_id=result.broker_order_id,
                        position_id=position.id,
                        paper=result.paper,
                    )
                    await signal_service.mark_acted(signal)
            except Exception as exc:  # noqa: BLE001 - always leave a trace on the signal
                _logger.error("handle_buy failed for user %s/%s: %s", event.user_id, event.ticker, exc)
                async with self._db.transaction() as session:
                    failed = await SignalRepository(session).get_by_id(signal_id)
                    if failed is not None and failed.status == SignalStatus.new.value:
                        await SignalService(session).mark_blocked(failed, reason=str(exc))
                return

            await self._publish(
                OrderFilledEvent(
                    user_id=event.user_id,
                    ticker=event.ticker,
                    side="buy",
                    quantity=quantity,
                    price=fill_price,
                    paper=result.paper,
                )
            )

    async def handle_sell(self, event: SellSignalEvent) -> None:
        async with self._lock(event.user_id, event.ticker, event.asset_class):
            # No dedup check for sells (unlike handle_buy) — a legitimate partial exit
            # followed shortly by a second sell of the remainder is normal, expected
            # behavior, not signal spam; selling is already naturally gated below by
            # requiring an open position.
            async with self._db.transaction() as session:
                signal_service = SignalService(session)
                signal = await signal_service.store_from_event(event)
                signal_id = signal.id

            try:
                async with self._db.transaction() as session:
                    positions = PositionRepository(session)
                    orders = OrderRepository(session)
                    signal_service = SignalService(session)
                    signal = await SignalRepository(session).get_by_id(signal_id)

                    position = await positions.get_open_by_ticker(
                        event.user_id, event.ticker, event.asset_class
                    )
                    if position is None:
                        await signal_service.mark_blocked(signal, reason="no open position")
                        await self._reject(event.ticker, event.user_id, "sell", "no open position")
                        return

                    if event.profit_tier is not None and getattr(
                        position, f"profit_tier{event.profit_tier}_taken"
                    ):
                        # Reloaded fresh under this ticker's lock — if it's already
                        # marked, a concurrent/overlapping strategy evaluation raced
                        # this same tier and already won (bugs.md finding 7). Without
                        # this check a second identical tier event would sell the
                        # configured percentage of whatever remains all over again.
                        reason = f"profit tier {event.profit_tier} already taken"
                        await signal_service.mark_blocked(signal, reason=reason)
                        await self._reject(event.ticker, event.user_id, "sell", reason)
                        return

                    if event.quantity_pct is None:
                        quantity = position.quantity
                    else:
                        quantity = min(position.quantity, position.quantity * event.quantity_pct / 100.0)
                    if quantity <= 0:
                        await signal_service.mark_blocked(signal, reason="zero quantity")
                        await self._reject(event.ticker, event.user_id, "sell", "zero quantity")
                        return

                    price = float(await _maybe_await(self._quote(event.ticker)))
                    broker = await _maybe_await(self._resolve_broker(event.user_id, event.asset_class))

                    result = await broker.place_market_order(
                        event.ticker, -quantity, asset_class=event.asset_class
                    )
                    if result.status == OrderStatus.rejected.value:
                        reason = result.reason or "broker rejected"
                        await signal_service.mark_blocked(signal, reason=reason)
                        await self._reject(event.ticker, event.user_id, "sell", reason)
                        return

                    if result.status != OrderStatus.filled.value:
                        await orders.create(
                            user_id=event.user_id,
                            ticker=event.ticker,
                            asset_class=event.asset_class,
                            side=OrderSide.sell.value,
                            quantity=quantity,
                            price=result.avg_price,
                            status=_normalize_order_status(result.status),
                            broker_order_id=result.broker_order_id,
                            position_id=position.id,
                            paper=result.paper,
                        )
                        await signal_service.mark_acted(signal)
                        return

                    fill_price = result.avg_price or price
                    remaining = position.quantity - quantity
                    now = datetime.now(timezone.utc)
                    if remaining <= 1e-9:
                        await positions.update(
                            position,
                            quantity=0.0,
                            status=PositionStatus.closed.value,
                            closed_at=now,
                        )
                    else:
                        await positions.update(position, quantity=remaining)

                    if event.profit_tier is not None:
                        await positions.mark_tier_taken(position, event.profit_tier)

                    await orders.create(
                        user_id=event.user_id,
                        ticker=event.ticker,
                        side=OrderSide.sell.value,
                        quantity=quantity,
                        price=fill_price,
                        status=OrderStatus.filled.value,
                        broker_order_id=result.broker_order_id,
                        position_id=position.id,
                        paper=result.paper,
                    )
                    await signal_service.mark_acted(signal)
            except Exception as exc:  # noqa: BLE001 - always leave a trace on the signal
                _logger.error("handle_sell failed for user %s/%s: %s", event.user_id, event.ticker, exc)
                async with self._db.transaction() as session:
                    failed = await SignalRepository(session).get_by_id(signal_id)
                    if failed is not None and failed.status == SignalStatus.new.value:
                        await SignalService(session).mark_blocked(failed, reason=str(exc))
                return

            await self._publish(
                OrderFilledEvent(
                    user_id=event.user_id,
                    ticker=event.ticker,
                    side="sell",
                    quantity=quantity,
                    price=fill_price,
                    paper=result.paper,
                )
            )

    async def place_manual_order(
        self,
        *,
        user_id: int,
        ticker: str,
        side: str,
        quantity: float,
        asset_class: str = AssetClass.equity.value,
    ) -> dict[str, Any]:
        """User-initiated buy/sell for an exact ``quantity`` (no auto-sizing, no
        dedup window — this is an explicit one-off action, not a strategy signal).
        Reuses the same per-``(user_id, ticker)`` lock and broker resolution as
        ``handle_buy``/``handle_sell``, and records a ``Signal`` with
        ``source="manual"`` so it shows up in the same audit trail."""
        if side not in (OrderSide.buy.value, OrderSide.sell.value):
            raise ManualOrderError(f"invalid side '{side}'")
        if quantity <= 0:
            raise ManualOrderError("quantity must be positive")

        async with self._lock(user_id, ticker, asset_class):
            async with self._db.transaction() as session:
                signal = await SignalService(session).store(
                    user_id=user_id,
                    ticker=ticker,
                    direction=side,
                    source="manual",
                    asset_class=asset_class,
                    reasoning="manual order placed by user",
                )
                signal_id = signal.id

            try:
                async with self._db.transaction() as session:
                    positions = PositionRepository(session)
                    orders = OrderRepository(session)
                    signal_service = SignalService(session)
                    signal = await SignalRepository(session).get_by_id(signal_id)

                    position = await positions.get_open_by_ticker(user_id, ticker, asset_class)

                    if side == OrderSide.sell.value:
                        if position is None or position.quantity <= 0:
                            await signal_service.mark_blocked(signal, reason="no open position to sell")
                            raise ManualOrderError("no open position to sell")
                        if quantity > position.quantity + 1e-9:
                            await signal_service.mark_blocked(
                                signal, reason="quantity exceeds position size"
                            )
                            raise ManualOrderError(
                                f"cannot sell {quantity}; only {position.quantity} held"
                            )

                    broker = await _maybe_await(self._resolve_broker(user_id, asset_class))
                    broker_qty = quantity if side == OrderSide.buy.value else -quantity
                    result = await broker.place_market_order(ticker, broker_qty, asset_class=asset_class)
                    if result.status == OrderStatus.rejected.value:
                        reason = result.reason or "broker rejected"
                        await signal_service.mark_blocked(signal, reason=reason)
                        raise ManualOrderError(reason)

                    if result.status != OrderStatus.filled.value:
                        # Not yet confirmed filled — persist as pending, don't touch
                        # position state; reconcile_pending_orders finalizes it later.
                        order = await orders.create(
                            user_id=user_id,
                            ticker=ticker,
                            asset_class=asset_class,
                            side=side,
                            quantity=quantity,
                            price=result.avg_price,
                            status=_normalize_order_status(result.status),
                            broker_order_id=result.broker_order_id,
                            position_id=position.id if position else None,
                            paper=result.paper,
                        )
                        await signal_service.mark_acted(signal)
                        return {
                            "id": order.id,
                            "ticker": order.ticker,
                            "side": order.side,
                            "quantity": order.quantity,
                            "price": order.price,
                            "status": order.status,
                            "paper": order.paper,
                        }

                    fill_price = result.avg_price
                    if fill_price is None:
                        fill_price = float(await _maybe_await(self._quote(ticker)))
                    now = datetime.now(timezone.utc)

                    if side == OrderSide.buy.value:
                        if position is None:
                            position = await positions.create(
                                user_id=user_id,
                                ticker=ticker,
                                asset_class=asset_class,
                                quantity=quantity,
                                avg_price=fill_price,
                                high_water_mark=fill_price,
                                status=PositionStatus.open.value,
                                opened_at=now,
                            )
                        else:
                            total_qty = position.quantity + quantity
                            new_avg = (
                                position.avg_price * position.quantity + fill_price * quantity
                            ) / total_qty
                            position = await positions.update(
                                position, quantity=total_qty, avg_price=new_avg
                            )
                    else:
                        remaining = position.quantity - quantity
                        if remaining <= 1e-9:
                            position = await positions.update(
                                position,
                                quantity=0.0,
                                status=PositionStatus.closed.value,
                                closed_at=now,
                            )
                        else:
                            position = await positions.update(position, quantity=remaining)

                    order = await orders.create(
                        user_id=user_id,
                        ticker=ticker,
                        asset_class=asset_class,
                        side=side,
                        quantity=quantity,
                        price=fill_price,
                        status=OrderStatus.filled.value,
                        broker_order_id=result.broker_order_id,
                        position_id=position.id,
                        paper=result.paper,
                    )
                    await signal_service.mark_acted(signal)
            except ManualOrderError:
                raise
            except Exception as exc:  # noqa: BLE001 - always leave a trace on the signal
                _logger.error(
                    "place_manual_order failed for user %s/%s: %s", user_id, ticker, exc
                )
                async with self._db.transaction() as session:
                    failed = await SignalRepository(session).get_by_id(signal_id)
                    if failed is not None and failed.status == SignalStatus.new.value:
                        await SignalService(session).mark_blocked(failed, reason=str(exc))
                raise ManualOrderError(str(exc)) from exc

        await self._publish(
            OrderFilledEvent(
                user_id=user_id,
                ticker=ticker,
                side=side,
                quantity=quantity,
                price=fill_price,
                paper=result.paper,
            )
        )
        return {
            "id": order.id,
            "ticker": order.ticker,
            "side": order.side,
            "quantity": order.quantity,
            "price": order.price,
            "status": order.status,
            "paper": order.paper,
        }

    async def reconcile_pending_orders(self) -> None:
        """Poll the broker for every order still recorded as ``pending`` (see
        handle_buy/handle_sell/place_manual_order) and finalize it: apply the
        position mutation only once the broker confirms ``filled``; mark
        ``rejected``/``cancelled`` orders as such with no position change; leave a
        still-pending order untouched for the next pass."""
        async with self._db.session() as session:
            pending = await OrderRepository(session).list_pending()
        for order in pending:
            if not order.broker_order_id:
                continue
            try:
                broker = await _maybe_await(self._resolve_broker(order.user_id, order.asset_class))
                result = await broker.get_order_status(order.broker_order_id)
            except Exception as exc:  # noqa: BLE001 - try the rest, this one stays pending
                _logger.warning("reconcile: status check failed for order %s: %s", order.id, exc)
                continue
            async with self._lock(order.user_id, order.ticker, order.asset_class):
                try:
                    await self._apply_reconciled_order(order.id, result)
                except Exception as exc:  # noqa: BLE001 - never let one bad order stop the batch
                    _logger.error("reconcile: failed to apply order %s: %s", order.id, exc)

    async def _apply_reconciled_order(self, order_id: int, result: Any) -> None:
        fill_event_kwargs: dict[str, Any] | None = None
        async with self._db.transaction() as session:
            orders = OrderRepository(session)
            order = await orders.get_by_id(order_id)
            if order is None or order.status != OrderStatus.pending.value:
                return  # already reconciled by a previous/concurrent pass

            if result.status in (OrderStatus.rejected.value, OrderStatus.cancelled.value):
                await orders.update(order, status=result.status)
                await self._publish(
                    OrderRejectedEvent(
                        user_id=order.user_id,
                        ticker=order.ticker,
                        side=order.side,
                        reason=result.reason or f"broker reported {result.status}",
                    )
                )
                return

            if result.status != OrderStatus.filled.value:
                return  # still pending — nothing to do yet

            positions = PositionRepository(session)
            fill_price = result.avg_price or order.price or 0.0
            now = datetime.now(timezone.utc)
            position = await positions.get_open_by_ticker(order.user_id, order.ticker, order.asset_class)

            if order.side == OrderSide.buy.value:
                if position is None:
                    position = await positions.create(
                        user_id=order.user_id,
                        ticker=order.ticker,
                        asset_class=order.asset_class,
                        quantity=order.quantity,
                        avg_price=fill_price,
                        high_water_mark=fill_price,
                        status=PositionStatus.open.value,
                        opened_at=now,
                    )
                else:
                    total_qty = position.quantity + order.quantity
                    new_avg = (
                        position.avg_price * position.quantity + fill_price * order.quantity
                    ) / total_qty
                    position = await positions.update(position, quantity=total_qty, avg_price=new_avg)
            else:
                if position is None:
                    # Position was already fully closed by something else in the
                    # meantime (e.g. a manual sell) — nothing left to reduce.
                    _logger.warning(
                        "reconcile: sell order %s filled but no open position for %s/%s",
                        order.id,
                        order.user_id,
                        order.ticker,
                    )
                else:
                    remaining = position.quantity - order.quantity
                    if remaining <= 1e-9:
                        position = await positions.update(
                            position, quantity=0.0, status=PositionStatus.closed.value, closed_at=now
                        )
                    else:
                        position = await positions.update(position, quantity=remaining)

            fill_event_kwargs = {
                "user_id": order.user_id,
                "ticker": order.ticker,
                "side": order.side,
                "quantity": order.quantity,
                "price": fill_price,
                "paper": order.paper,
            }
            await orders.update(
                order,
                status=OrderStatus.filled.value,
                price=fill_price,
                position_id=position.id if position is not None else order.position_id,
            )

        if fill_event_kwargs is not None:
            await self._publish(OrderFilledEvent(**fill_event_kwargs))


__all__ = ["ExecutionEngine", "ManualOrderError"]
