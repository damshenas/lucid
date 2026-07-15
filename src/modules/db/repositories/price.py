"""Price watchlist and fetch-log repositories."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..models.price import PriceFetchAttempt, PriceFetchLog, PriceWatchlist
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

    async def upsert(
        self,
        ticker: str,
        *,
        asset_class: str,
        enabled: bool = True,
        poll_interval: str = "1h",
        region: str = "us",
    ) -> PriceWatchlist:
        """Add a ticker to the watchlist, or update its asset class/enabled
        flag/poll interval/region if it's already there — this is what makes a ticker
        a *buy-side* candidate: polled for prices (see TradingRuntime._pipeline, which
        also covers any ticker with an open position regardless of watchlist
        membership) and evaluated by active buy strategies (see
        TradingRuntime.run_strategies). Sell strategies don't need a watchlist entry
        at all — they run over the user's open positions directly."""
        ticker = ticker.upper()
        existing = await self.get_by_ticker(ticker)
        if existing is not None:
            existing.asset_class = asset_class
            existing.enabled = enabled
            existing.poll_interval = poll_interval
            existing.region = region
            await self.session.flush()
            return existing
        return await self.create(
            ticker=ticker,
            asset_class=asset_class,
            enabled=enabled,
            poll_interval=poll_interval,
            region=region,
        )

    async def set_enabled(self, ticker: str, enabled: bool) -> PriceWatchlist | None:
        row = await self.get_by_ticker(ticker.upper())
        if row is None:
            return None
        row.enabled = enabled
        await self.session.flush()
        return row

    async def set_poll_interval(self, ticker: str, poll_interval: str) -> PriceWatchlist | None:
        row = await self.get_by_ticker(ticker.upper())
        if row is None:
            return None
        row.poll_interval = poll_interval
        await self.session.flush()
        return row

    async def set_region(self, ticker: str, region: str) -> PriceWatchlist | None:
        row = await self.get_by_ticker(ticker.upper())
        if row is None:
            return None
        row.region = region
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


class PriceFetchAttemptRepository(BaseRepository[PriceFetchAttempt]):
    model = PriceFetchAttempt

    async def record(
        self,
        *,
        ticker: str,
        interval: str,
        status: str,
        duration_seconds: float = 0.0,
        rows_fetched: int = 0,
        error_message: str | None = None,
        attempted_at: datetime | None = None,
    ) -> PriceFetchAttempt:
        return await self.create(
            ticker=ticker,
            interval=interval,
            status=status,
            duration_seconds=duration_seconds,
            rows_fetched=rows_fetched,
            error_message=error_message,
            attempted_at=attempted_at or datetime.now(timezone.utc),
        )

    async def list_recent(self, *, days: int = 7, limit: int = 500) -> list[PriceFetchAttempt]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(PriceFetchAttempt)
            .where(PriceFetchAttempt.attempted_at >= cutoff)
            .order_by(PriceFetchAttempt.attempted_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
