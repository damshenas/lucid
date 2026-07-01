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
