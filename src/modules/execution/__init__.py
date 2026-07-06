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


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


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

    def _lock(self, user_id: int, ticker: str) -> asyncio.Lock:
        key = (user_id, ticker)
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
        async with self._lock(event.user_id, event.ticker):
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

                    if await positions.get_open_by_ticker(event.user_id, event.ticker) is not None:
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

                    fill_price = result.avg_price or price
                    now = datetime.now(timezone.utc)
                    position = await positions.create(
                        user_id=event.user_id,
                        ticker=event.ticker,
                        asset_class=event.asset_class,
                        quantity=quantity,
                        avg_price=fill_price,
                        status=PositionStatus.open.value,
                        opened_at=now,
                    )
                    await orders.create(
                        user_id=event.user_id,
                        ticker=event.ticker,
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
        async with self._lock(event.user_id, event.ticker):
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

                    position = await positions.get_open_by_ticker(event.user_id, event.ticker)
                    if position is None:
                        await signal_service.mark_blocked(signal, reason="no open position")
                        await self._reject(event.ticker, event.user_id, "sell", "no open position")
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


__all__ = ["ExecutionEngine"]
