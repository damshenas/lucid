"""Price watchlist and fetch-log repositories."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from ..models.price import PriceFetchLog, PriceWatchlist
from .base import BaseRepository


class PriceWatchlistRepository(BaseRepository[PriceWatchlist]):
    model = PriceWatchlist

    async def get_by_ticker(self, ticker: str) -> PriceWatchlist | None:
        stmt = select(PriceWatchlist).where(PriceWatchlist.ticker == ticker)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_enabled(self) -> list[PriceWatchlist]:
        stmt = select(PriceWatchlist).where(PriceWatchlist.enabled.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[PriceWatchlist]:
        stmt = select(PriceWatchlist).order_by(PriceWatchlist.ticker)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(self, ticker: str, *, asset_class: str, enabled: bool = True) -> PriceWatchlist:
        """Add a ticker to the watchlist, or update its asset class/enabled flag if
        it's already there — this is what makes a ticker actually get its price
        polled (see TradingRuntime._pipeline) and evaluated by strategies (see
        TradingRuntime.run_strategies); without an entry here, nothing ever happens
        for that ticker regardless of which strategy is active."""
        ticker = ticker.upper()
        existing = await self.get_by_ticker(ticker)
        if existing is not None:
            existing.asset_class = asset_class
            existing.enabled = enabled
            await self.session.flush()
            return existing
        return await self.create(ticker=ticker, asset_class=asset_class, enabled=enabled)

    async def set_enabled(self, ticker: str, enabled: bool) -> PriceWatchlist | None:
        row = await self.get_by_ticker(ticker.upper())
        if row is None:
            return None
        row.enabled = enabled
        await self.session.flush()
        return row

    async def delete_by_ticker(self, ticker: str) -> bool:
        row = await self.get_by_ticker(ticker.upper())
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True


class PriceFetchLogRepository(BaseRepository[PriceFetchLog]):
    model = PriceFetchLog

    async def mark_fetched(
        self, ticker: str, interval: str, when: datetime | None = None
    ) -> PriceFetchLog:
        when = when or datetime.now(timezone.utc)
        stmt = select(PriceFetchLog).where(
            PriceFetchLog.ticker == ticker, PriceFetchLog.interval == interval
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return await self.create(ticker=ticker, interval=interval, last_fetched_at=when)
        row.last_fetched_at = when
        await self.session.flush()
        return row
