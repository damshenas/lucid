"""Watchlist-driven price pipelines: ``run_daily`` / ``run_intraday`` / ``run_backfill``.

Fetching and the watchlist source are injected so the pipeline stays free of DB and
network coupling and is easy to test.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

import pandas as pd

from src.modules.bus import EventBus, PriceFetchedEvent
from src.modules.logger import get_logger

from . import storage

Fetcher = Callable[..., Awaitable[pd.DataFrame] | pd.DataFrame]
WatchlistProvider = Callable[[], Awaitable[list[str]] | list[str]]
OnFetched = Callable[[str, str, int], Awaitable[None] | None]

_logger = get_logger("price.pipeline")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class PricePipeline:
    """Required: ``storage_path``, ``fetcher``, ``watchlist_provider``.

    Optional: ``bus`` (emits ``PriceFetchedEvent``), ``on_fetched`` (e.g. update the
    fetch log).
    """

    def __init__(
        self,
        *,
        storage_path: str,
        fetcher: Fetcher,
        watchlist_provider: WatchlistProvider,
        bus: EventBus | None = None,
        on_fetched: OnFetched | None = None,
    ) -> None:
        self._storage_path = storage_path
        self._fetch = fetcher
        self._watchlist = watchlist_provider
        self._bus = bus
        self._on_fetched = on_fetched

    async def _store_and_notify(self, ticker: str, interval: str, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        storage.append_bars(self._storage_path, ticker, interval, df)
        rows = len(df)
        if self._on_fetched is not None:
            await _maybe_await(self._on_fetched(ticker, interval, rows))
        if self._bus is not None:
            await self._bus.publish(PriceFetchedEvent(ticker=ticker, interval=interval, rows=rows))
        return rows

    async def run_daily(self, *, period: str = "1y") -> dict[str, int]:
        results: dict[str, int] = {}
        for ticker in await _maybe_await(self._watchlist()):
            try:
                df = await _maybe_await(self._fetch(ticker, period=period, interval="1d"))
                results[ticker] = await self._store_and_notify(ticker, "1d", df)
            except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the run
                _logger.warning("daily fetch failed for %s: %s", ticker, exc)
                results[ticker] = 0
        return results

    async def run_intraday(self, *, interval: str = "15m", period: str = "5d") -> dict[str, int]:
        results: dict[str, int] = {}
        for ticker in await _maybe_await(self._watchlist()):
            try:
                df = await _maybe_await(self._fetch(ticker, period=period, interval=interval))
                results[ticker] = await self._store_and_notify(ticker, interval, df)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("intraday fetch failed for %s: %s", ticker, exc)
                results[ticker] = 0
        return results

    async def run_backfill(self, ticker: str, *, days: int = 365) -> int:
        df = await _maybe_await(self._fetch(ticker, period=f"{days}d", interval="1d"))
        return await self._store_and_notify(ticker, "1d", df)
