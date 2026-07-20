"""Shared exponential-backoff retry helper for external data connectors.

Mirrors the manual retry loop already proven in
``src/modules/com/trading212/__init__.py`` (backoff formula
``backoff_base * 2 ** (attempt - 1)``) so every connector that makes a real network
call (``com.finviz``/``com.tradingview`` directly; ``com.zacks``/``com.barchart``'s
disabled placeholders don't; anything routed through ``HttpDataProvider``) and the
yfinance wrapper can share one retry policy instead of each reimplementing it.

This is a per-connector retry mechanism only (respects each service's own quota/
rate limits) — deliberately *not* a system-wide circuit breaker.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE = 0.2


async def with_retry(
    attempt: Callable[[], Awaitable[T]],
    *,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Call ``attempt()`` up to ``retry_attempts`` times with exponential backoff
    between tries whenever it raises one of ``retryable_exceptions``. Any other
    exception propagates immediately, with no retry. Re-raises the last retryable
    exception once attempts are exhausted."""
    last_exc: Exception | None = None
    for n in range(1, retry_attempts + 1):
        try:
            return await attempt()
        except retryable_exceptions as exc:
            last_exc = exc
            if n < retry_attempts:
                await asyncio.sleep(backoff_base * (2 ** (n - 1)))
                continue
    assert last_exc is not None
    raise last_exc


__all__ = ["DEFAULT_BACKOFF_BASE", "DEFAULT_RETRY_ATTEMPTS", "with_retry"]
