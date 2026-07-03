"""Trading runtime: wires the execution engine to the bus and registers scheduled jobs.

Kept separate from ``create_app`` so the composition stays readable. The scheduler is
started only for a real (non-SQLite) database so the unit-test app stays free of
background jobs.
"""

from __future__ import annotations

from typing import Any

from src.modules.db.models.base import Role
from src.modules.db.repositories.price import PriceFetchLogRepository, PriceWatchlistRepository
from src.modules.db.repositories.position import PositionRepository
from src.modules.db.repositories.user import UserRepository
from src.modules.com import yahoofinance
from src.modules.com.git import sync_and_deploy
from src.modules.execution import ExecutionEngine
from src.modules.logger import get_logger
from src.modules.price import storage
from src.modules.price.pipeline import PricePipeline
from src.modules.schedules import Scheduler
from src.modules.strategy.context import PositionView, StrategyContext

from .context import AppContext

_logger = get_logger("runtime")


class TradingRuntime:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self.scheduler = Scheduler(timeout_seconds=ctx.settings.schedule.task_timeout_seconds)
        self.execution = ExecutionEngine(
            db=ctx.db,
            broker_resolver=self._broker,
            quote_provider=self._quote,
            config_provider=self._config,
            bus=ctx.bus,
        )

    # -- providers for the execution engine --------------------------------

    def _quote(self, ticker: str) -> float:
        df = storage.read_bars(self.ctx.settings.price.storage_path, ticker, "1d")
        if df is None or df.empty:
            return 0.0
        return float(df["close"].iloc[-1])

    async def _config(self, user_id: int, asset_class: str | None) -> dict[str, Any]:
        async with self.ctx.db.session() as session:
            return await self.ctx.config_service(session).compile_values(
                user_id=user_id, asset_class=asset_class
            )

    async def _broker(self, user_id: int, asset_class: str):
        async with self.ctx.db.session() as session:
            return await self.ctx.resolve_broker(session, user_id, asset_class)

    # -- scheduled jobs ----------------------------------------------------

    async def _watchlist(self) -> list[str]:
        async with self.ctx.db.session() as session:
            rows = await PriceWatchlistRepository(session).list_enabled()
        return [r.ticker for r in rows]

    async def _mark_fetched(self, ticker: str, interval: str, _rows: int) -> None:
        async with self.ctx.db.transaction() as session:
            await PriceFetchLogRepository(session).mark_fetched(ticker, interval)

    def _pipeline(self) -> PricePipeline:
        return PricePipeline(
            storage_path=self.ctx.settings.price.storage_path,
            fetcher=yahoofinance.fetch_ohlcv,
            watchlist_provider=self._watchlist,
            bus=self.ctx.bus,
            on_fetched=self._mark_fetched,
        )

    async def run_strategies(self) -> None:
        """Run active buy/sell strategies for each trader over the watchlist."""
        async with self.ctx.db.session() as session:
            users = [
                u
                for u in await UserRepository(session).get_all()
                if u.role == Role.trader.value and u.is_active
            ]
            watchlist = await PriceWatchlistRepository(session).list_enabled()
            strat_service = self.ctx.strategy_service(session)

        storage_path = self.ctx.settings.price.storage_path
        for user in users:
            try:
                values = await self._config(user.id, "equity")
            except Exception as exc:  # noqa: BLE001
                _logger.warning("config load failed for user %s: %s", user.id, exc)
                continue
            buy = strat_service.get_active(values, "buy")
            sell = strat_service.get_active(values, "sell")

            for item in watchlist:
                df = storage.read_bars(storage_path, item.ticker, "1d")
                if df is None or df.empty:
                    continue
                try:
                    await self._evaluate_ticker(user.id, item, df, values, buy, sell)
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("strategy eval failed %s/%s: %s", user.id, item.ticker, exc)

    async def _evaluate_ticker(self, user_id, item, df, values, buy, sell) -> None:
        if sell is not None:
            async with self.ctx.db.session() as session:
                position = await PositionRepository(session).get_open_by_ticker(user_id, item.ticker)
            if position is not None:
                sell_signal = await sell.run(
                    StrategyContext(
                        ticker=item.ticker,
                        user_id=user_id,
                        asset_class=item.asset_class,
                        config=values,
                        price_data=df,
                        position=PositionView(item.ticker, position.quantity, position.avg_price),
                    )
                )
                if sell_signal is not None:
                    await self.ctx.bus.publish(sell_signal)

        if buy is not None:
            buy_signal = await buy.run(
                StrategyContext(
                    ticker=item.ticker,
                    user_id=user_id,
                    asset_class=item.asset_class,
                    config=values,
                    price_data=df,
                )
            )
            if buy_signal is not None:
                await self.ctx.bus.publish(buy_signal)

    async def _scan_strategies(self) -> None:
        async with self.ctx.db.transaction() as session:
            await self.ctx.strategy_service(session).scan()

    async def git_sync(self) -> tuple[str, list[str]]:
        """Pull the already-cloned ``EXT_STRATEGIES`` checkout, then deploy into strategies.

        On-demand only (triggered by an admin via ``POST /api/v1/admin/git-sync``) —
        there is no recurring schedule, and unlike the startup sync this ignores
        ``git_sync.enabled`` (that flag only gates the automatic startup sync in
        ``src/scripts/sync_algorithms.py``): clicking the button is itself the
        admin's explicit consent, so it must not depend on a separate setting having
        been saved first. The staging mount (``EXT_STRATEGIES``) is never executed
        from directly; only files copied into ``STRATEGIES_ROOT`` by
        ``deploy_strategies`` are loaded.
        """
        commit, copied = await sync_and_deploy(
            staging_root=self.ctx.ext_strategies_root,
            target_root=self.ctx.strategies_root,
        )
        if copied:
            await self._scan_strategies()
        _logger.info("git sync complete at %s (%d file(s) updated)", commit[:8], len(copied))
        return commit, copied

    def register_jobs(self) -> None:
        schedule = self.ctx.settings.schedule
        pipeline = self._pipeline()
        interval = self.ctx.settings.price.intraday_interval

        self.scheduler.add_cron_job(pipeline.run_daily, id="price_daily", hour=schedule.daily_price_hour)
        self.scheduler.add_interval_job(
            lambda: pipeline.run_intraday(interval=interval),
            id="price_intraday",
            minutes=max(1, schedule.intraday_price_minutes),
        )
        self.scheduler.add_cron_job(
            self._scan_strategies, id="strategy_scan", hour=schedule.strategy_scan_hour
        )
        self.scheduler.add_interval_job(
            self.run_strategies,
            id="run_strategies",
            seconds=max(30, schedule.poll_positions_seconds),
        )

    # -- lifecycle ---------------------------------------------------------

    def wire(self) -> None:
        self.execution.subscribe(self.ctx.bus)

    def start(self) -> None:
        self.register_jobs()
        self.scheduler.start()
        _logger.info("scheduler started with %d jobs", len(self.scheduler.job_list()))

    def shutdown(self) -> None:
        self.scheduler.shutdown()
