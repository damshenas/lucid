"""Trading runtime: wires the execution engine to the bus and registers scheduled jobs.

Kept separate from ``create_app`` so the composition stays readable. The scheduler is
started only for a real (non-SQLite) database so the unit-test app stays free of
background jobs.
"""

from __future__ import annotations

from typing import Any

from src.modules.db.models.base import Role
from src.modules.db.repositories.decision import StrategyDecisionRepository
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
from src.modules.signal.sources import ExternalSignal, SignalSourceRegistry
from src.modules.strategy.context import PositionView, StrategyContext, StrategyDecision
from src.modules.strategy.loader import LoadedStrategy

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
        """Tickers the price pipeline keeps fetching: the (buy-screening) watchlist
        plus every ticker any user currently holds an open position in — so a held
        position keeps getting fresh bars (and can still be sold) even after it's
        removed from the watchlist (see run_strategies below)."""
        async with self.ctx.db.session() as session:
            watchlist_tickers = {r.ticker for r in await PriceWatchlistRepository(session).list_enabled()}
            position_tickers = {r.ticker for r in await PositionRepository(session).list_all_open()}
        return sorted(watchlist_tickers | position_tickers)

    async def _watchlist_by_poll_interval(self, poll_interval: str) -> list[str]:
        """Enabled watchlist tickers set (Settings > Price > Watchlist) to this
        intraday granularity — "1m" (green chip) or "1h" (blue chip, the default).
        Independent of the always-on daily ("1d") fetch every watchlist ticker gets
        via ._watchlist() above regardless of this per-ticker choice."""
        async with self.ctx.db.session() as session:
            rows = await PriceWatchlistRepository(session).list_enabled()
        return [r.ticker for r in rows if r.poll_interval == poll_interval]

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

    def _intraday_pipeline(self, poll_interval: str) -> PricePipeline:
        """A pipeline scoped to one intraday granularity ('1m'/'1h') — its
        watchlist_provider only ever returns tickers configured for that granularity
        (see ._watchlist_by_poll_interval), unlike ._pipeline() above (daily bars,
        every watchlist ticker + open positions, regardless of poll_interval)."""
        return PricePipeline(
            storage_path=self.ctx.settings.price.storage_path,
            fetcher=yahoofinance.fetch_ohlcv,
            watchlist_provider=lambda: self._watchlist_by_poll_interval(poll_interval),
            bus=self.ctx.bus,
            on_fetched=self._mark_fetched,
        )

    async def run_strategies(self) -> None:
        """Run each trader's active sell strategy over their own open positions, and
        their active buy strategy over the (shared) price watchlist.

        These two have deliberately different ticker sources: a sell strategy only
        ever needs to look at what a user already holds (``PositionRepository.
        list_all_open`` — a position is itself the "universe", nothing extra to
        configure), so it's independent of the watchlist and runs even for a ticker
        that was never added there or was later removed from it. A buy strategy has
        no such built-in universe — deciding what to *consider* buying requires a
        user-curated list of candidate tickers, which is exactly what the watchlist
        is for (Prices page > Watchlist / ``GET-POST-PATCH-DELETE /api/v1/prices/
        watchlist``). Activating a strategy alone is therefore only a no-op for the
        buy side when the watchlist is empty — the sell side always runs.
        """
        async with self.ctx.db.session() as session:
            users = [
                u
                for u in await UserRepository(session).get_all()
                if u.role == Role.trader.value and u.is_active
            ]
            watchlist = await PriceWatchlistRepository(session).list_enabled()
            strat_service = self.ctx.strategy_service(session)

        _logger.debug(
            "run_strategies: %d trader(s), %d enabled watchlist ticker(s): %s",
            len(users),
            len(watchlist),
            [w.ticker for w in watchlist],
        )
        if not watchlist:
            _logger.debug(
                "run_strategies: watchlist is empty — no *buy* signal will ever be "
                "produced until a candidate ticker is added (Prices page > Watchlist); "
                "sell strategies are unaffected, they run over open positions instead"
            )

        storage_path = self.ctx.settings.price.storage_path
        for user in users:
            try:
                values = await self._config(user.id, "equity")
            except Exception as exc:  # noqa: BLE001
                _logger.warning("config load failed for user %s: %s", user.id, exc)
                continue
            buy = strat_service.get_active(values, "buy")
            sell = strat_service.get_active(values, "sell")
            _logger.debug(
                "run_strategies: user=%s active_buy=%s active_sell=%s",
                user.id,
                buy.name if buy else None,
                sell.name if sell else None,
            )
            if buy is None and sell is None:
                continue

            if sell is not None:
                async with self.ctx.db.session() as session:
                    positions = await PositionRepository(session).list_open(user.id)
                for position in positions:
                    df = storage.read_bars(storage_path, position.ticker, "1d")
                    if df is None or df.empty:
                        _logger.debug(
                            "run_strategies: no stored bars for held position %s — skipping "
                            "(it stays queued for the next price fetch, see ._watchlist)",
                            position.ticker,
                        )
                        continue
                    try:
                        await self._evaluate_sell(user.id, position, df, values, sell)
                    except Exception as exc:  # noqa: BLE001
                        _logger.warning("sell strategy eval failed %s/%s: %s", user.id, position.ticker, exc)

            if buy is not None:
                for item in watchlist:
                    df = storage.read_bars(storage_path, item.ticker, "1d")
                    if df is None or df.empty:
                        _logger.debug(
                            "run_strategies: no stored bars for %s — skipping (backfill it first)",
                            item.ticker,
                        )
                        continue
                    try:
                        await self._evaluate_buy(user.id, item, df, values, buy)
                    except Exception as exc:  # noqa: BLE001
                        _logger.warning("buy strategy eval failed %s/%s: %s", user.id, item.ticker, exc)

    async def _external_signals(
        self, user_id: int, ticker: str, sources: list[str]
    ) -> list[ExternalSignal]:
        """Fetch third-party ratings (finviz/tradingview/zacks/barchart — see
        src/modules/signal/sources.py) for the sources a strategy declared via its
        optional ``EXTERNAL_SOURCES`` module attribute. Returns ``[]`` (never raises)
        when the strategy didn't ask for any, or when fetching fails outright — a
        strategy must treat a missing/errored source as "no opinion", not crash."""
        if not sources:
            return []
        try:
            async with self.ctx.db.session() as session:
                registry = SignalSourceRegistry(self.ctx.credential_manager(session), user_id=user_id)
                return await registry.fetch(ticker, sources)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("external signal fetch failed for %s/%s: %s", user_id, ticker, exc)
            return []

    async def _evaluate_sell(self, user_id: int, position, df, values, sell: LoadedStrategy) -> None:
        external = await self._external_signals(user_id, position.ticker, sell.external_sources)
        sell_decision = await sell.run(
            StrategyContext(
                ticker=position.ticker,
                user_id=user_id,
                asset_class=position.asset_class,
                config=values,
                price_data=df,
                position=PositionView(position.ticker, position.quantity, position.avg_price),
                external_signals=external,
            )
        )
        await self._record_decision(user_id, position, sell.name, "sell", sell_decision)
        if sell_decision.acted and sell_decision.event is not None:
            _logger.debug("run_strategies: %s sell signal for %s", sell.name, position.ticker)
            await self.ctx.bus.publish(sell_decision.event)

    async def _evaluate_buy(self, user_id: int, item, df, values, buy: LoadedStrategy) -> None:
        external = await self._external_signals(user_id, item.ticker, buy.external_sources)
        buy_decision = await buy.run(
            StrategyContext(
                ticker=item.ticker,
                user_id=user_id,
                asset_class=item.asset_class,
                config=values,
                price_data=df,
                external_signals=external,
            )
        )
        await self._record_decision(user_id, item, buy.name, "buy", buy_decision)
        if buy_decision.acted and buy_decision.event is not None:
            _logger.debug("run_strategies: %s buy signal for %s", buy.name, item.ticker)
            await self.ctx.bus.publish(buy_decision.event)

    async def _record_decision(
        self, user_id: int, item, strategy_name: str, direction: str, decision: StrategyDecision
    ) -> None:
        """Log a strategy's evaluation outcome — but only when it actually changed
        from the last one recorded for this (user, ticker, strategy), so a strategy
        that keeps deciding the same thing every poll doesn't spam the decision log
        (see pages/StrategyDetail.tsx) with thousands of identical rows."""
        async with self.ctx.db.transaction() as session:
            repo = StrategyDecisionRepository(session)
            latest = await repo.latest_for(user_id, item.ticker, strategy_name)
            if (
                latest is not None
                and latest.acted == decision.acted
                and latest.reasoning == decision.reasoning
            ):
                return
            await repo.create(
                user_id=user_id,
                ticker=item.ticker,
                asset_class=item.asset_class,
                strategy_name=strategy_name,
                direction=direction,
                acted=decision.acted,
                reasoning=decision.reasoning,
            )

    async def _scan_strategies(self) -> None:
        async with self.ctx.db.transaction() as session:
            await self.ctx.strategy_service(session).scan()

    async def git_sync(self) -> tuple[str, list[str]]:
        """Pull the already-cloned ``EXT_STRATEGIES`` checkout, then deploy into strategies.

        On-demand only (triggered by an admin via ``POST /api/v1/admin/git-sync``) —
        there is no recurring schedule and no enable/disable setting; clicking the
        button is itself the admin's explicit consent. The staging mount
        (``EXT_STRATEGIES``) is never executed from directly; only files copied into
        ``STRATEGIES_ROOT`` by ``deploy_strategies`` are loaded.
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
        daily_pipeline = self._pipeline()
        minute_pipeline = self._intraday_pipeline("1m")
        hourly_pipeline = self._intraday_pipeline("1h")

        self.scheduler.add_cron_job(
            daily_pipeline.run_daily, id="price_daily", hour=schedule.daily_price_hour
        )
        # Two separate jobs (rather than one shared "intraday" job) since each ticker
        # on the watchlist declares its own granularity (Settings > Price >
        # Watchlist) — a ticker only ever gets fetched by the job matching its
        # current choice, never both.
        self.scheduler.add_interval_job(
            lambda: minute_pipeline.run_intraday(interval="1m", period="5d"),
            id="price_intraday_1m",
            minutes=max(1, schedule.intraday_price_minutes),
        )
        self.scheduler.add_interval_job(
            lambda: hourly_pipeline.run_intraday(interval="1h", period="5d"),
            id="price_intraday_1h",
            minutes=max(1, schedule.intraday_price_minutes),
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
