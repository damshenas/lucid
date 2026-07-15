"""Watchlist-driven price pipelines: ``run_daily`` / ``run_intraday`` / ``run_backfill``.

Fetching and the watchlist source are injected so the pipeline stays free of DB and
network coupling and is easy to test.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

import pandas as pd

from src.modules.bus import EventBus, PriceFetchedEvent
from src.modules.logger import get_logger

from . import storage

Fetcher = Callable[..., Awaitable[pd.DataFrame] | pd.DataFrame]
WatchlistProvider = Callable[[], Awaitable[list[str]] | list[str]]
OnFetched = Callable[[str, str, int, float], Awaitable[None] | None]
OnError = Callable[[str, str, str, float], Awaitable[None] | None]

_logger = get_logger("price.pipeline")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class PricePipeline:
    """Required: ``storage_path``, ``fetcher``, ``watchlist_provider``.

    Optional: ``bus`` (emits ``PriceFetchedEvent``), ``on_fetched`` (e.g. update the
    fetch log on success), ``on_error`` (e.g. record a failed fetch attempt) — both
    receive the attempt's wall-clock ``duration_seconds`` so callers can build a
    "fetch activity" report (see ``PriceFetchAttemptRepository``).
    """

    def __init__(
        self,
        *,
        storage_path: str,
        fetcher: Fetcher,
        watchlist_provider: WatchlistProvider,
        bus: EventBus | None = None,
        on_fetched: OnFetched | None = None,
        on_error: OnError | None = None,
    ) -> None:
        self._storage_path = storage_path
        self._fetch = fetcher
        self._watchlist = watchlist_provider
        self._bus = bus
        self._on_fetched = on_fetched
        self._on_error = on_error

    async def _store_and_notify(self, ticker: str, interval: str, df: pd.DataFrame, duration: float) -> int:
        if df is None or df.empty:
            if self._on_fetched is not None:
                await _maybe_await(self._on_fetched(ticker, interval, 0, duration))
            return 0
        storage.append_bars(self._storage_path, ticker, interval, df)
        rows = len(df)
        if self._on_fetched is not None:
            await _maybe_await(self._on_fetched(ticker, interval, rows, duration))
        if self._bus is not None:
            await self._bus.publish(PriceFetchedEvent(ticker=ticker, interval=interval, rows=rows))
        return rows

    async def run_daily(self, *, period: str = "1y") -> dict[str, int]:
        results: dict[str, int] = {}
        for ticker in await _maybe_await(self._watchlist()):
            started = time.monotonic()
            try:
                df = await _maybe_await(self._fetch(ticker, period=period, interval="1d"))
                results[ticker] = await self._store_and_notify(
                    ticker, "1d", df, time.monotonic() - started
                )
            except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the run
                _logger.warning("daily fetch failed for %s: %s", ticker, exc)
                results[ticker] = 0
                if self._on_error is not None:
                    await _maybe_await(
                        self._on_error(ticker, "1d", str(exc), time.monotonic() - started)
                    )
        return results

    async def run_intraday(self, *, interval: str = "15m", period: str = "5d") -> dict[str, int]:
        results: dict[str, int] = {}
        for ticker in await _maybe_await(self._watchlist()):
            started = time.monotonic()
            try:
                df = await _maybe_await(self._fetch(ticker, period=period, interval=interval))
                results[ticker] = await self._store_and_notify(
                    ticker, interval, df, time.monotonic() - started
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("intraday fetch failed for %s: %s", ticker, exc)
                results[ticker] = 0
                if self._on_error is not None:
                    await _maybe_await(
                        self._on_error(ticker, interval, str(exc), time.monotonic() - started)
                    )
        return results

    async def run_backfill(self, ticker: str, *, days: int = 365) -> int:
        started = time.monotonic()
        df = await _maybe_await(self._fetch(ticker, period=f"{days}d", interval="1d"))
        return await self._store_and_notify(ticker, "1d", df, time.monotonic() - started)
