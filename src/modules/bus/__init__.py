"""Async event bus with isolated handlers.

Handlers may be sync or async. A failing handler is logged and never blocks the others.
"""

from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TypeVar

from src.modules.logger import get_logger

from .events import (
    BuySignalEvent,
    Event,
    OrderFilledEvent,
    OrderRejectedEvent,
    PriceFetchedEvent,
    SellSignalEvent,
)

EventT = TypeVar("EventT", bound=Event)
Handler = Callable[[EventT], None | Awaitable[None]]

_logger = get_logger("bus")


class EventBus:
    def __init__(self, max_queue_size: int | None = None) -> None:
        self._handlers: dict[type[Event], list[Handler]] = defaultdict(list)
        self._max_queue_size = max_queue_size

    def subscribe(self, event_type: type[EventT], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[EventT], handler: Handler) -> None:
        if handler in self._handlers.get(event_type, []):
            self._handlers[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        handlers = list(self._handlers.get(type(event), []))
        if not handlers:
            return
        await asyncio.gather(*(self._dispatch(h, event) for h in handlers))

    async def _dispatch(self, handler: Handler, event: Event) -> None:
        try:
            result = handler(event)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # noqa: BLE001 - isolate handler failures
            _logger.error(
                "handler %r failed for %s: %s",
                getattr(handler, "__qualname__", handler),
                type(event).__name__,
                exc,
            )


__all__ = [
    "BuySignalEvent",
    "Event",
    "EventBus",
    "Handler",
    "OrderFilledEvent",
    "OrderRejectedEvent",
    "PriceFetchedEvent",
    "SellSignalEvent",
]
