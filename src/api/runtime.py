"""Trading runtime: wires the execution engine to the bus and registers scheduled jobs.

Kept separate from ``create_app`` so the composition stays readable. The scheduler is
started only for a real (non-SQLite) database so the unit-test app stays free of
background jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.modules.db.models.base import Role
from src.modules.db.repositories.decision import StrategyDecisionRepository
from src.modules.db.repositories.price import (
    PriceFetchAttemptRepository,
    PriceFetchLogRepository,
    PriceWatchlistRepository,
)
from src.modules.db.repositories.position import PositionRepository
from src.modules.db.repositories.user import UserRepository
from src.modules.com import yahoofinance
from src.modules.com.git import sync_and_deploy
from src.modules.execution import ExecutionEngine
from src.modules.logger import get_logger
from src.modules.price import storage
from src.modules.price.pipeline import PricePipeline
from src.modules.schedules import Scheduler, market_hours
from src.modules.signal.sources import ExternalSignal, SignalSourceRegistry
from src.modules.strategy.context import PositionView, StrategyContext, StrategyDecision
from src.modules.strategy.loader import LoadedStrategy

from .context import AppContext

_logger = get_logger("runtime")


@dataclass(slots=True)
class _DiscoveredCandidate:
    """Stand-in for a ``PriceWatchlist``/``Position`` row when a buy strategy
    discovers its own candidate tickers (``LoadedStrategy.uses_watchlist=False``)
    instead of iterating the shared watchlist — ``_evaluate_buy``/``_record_decision``
    only ever need ``.ticker``/``.asset_class`` off whatever "item" they're given.
    Every current external signal source is equity-only, hence the fixed default.
    """

    ticker: str
    asset_class: str = "equity"


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

    async def _quote(self, ticker: str) -> float:
        storage_path = self.ctx.settings.price.storage_path
        price = storage.latest_price(storage_path, ticker)
        if price is not None:
            return price
        # Nothing stored at all yet (e.g. a signal_follow-discovered candidate that
        # hasn't been through a scheduled fetch) — fetch it now instead of blocking
        # this buy with "no price" until the next scheduled pipeline run.
        try:
            await self._pipeline().run_backfill(ticker, days=5)
        except Exception as exc:  # noqa: BLE001 - fall through to "no price" below
            _logger.warning("on-demand price fetch failed for %s: %s", ticker, exc)
            return 0.0
        price = storage.latest_price(storage_path, ticker)
        return price if price is not None else 0.0

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
        plus every ticker any user currently holds an open position in, plus every
        ticker currently discoverable by any trader's active USES_WATCHLIST=False buy
        strategy (e.g. signal_follow) — so a held position keeps getting fresh bars
        (and can still be sold) even after it's removed from the watchlist (see
        run_strategies below), and a discovery-only candidate (never on the watchlist
        by design) still gets a stored price. Without the latter, ExecutionEngine.
        handle_buy's `_quote()` would find nothing and permanently reject every such
        buy signal with "no price"."""
        async with self.ctx.db.session() as session:
            watchlist_tickers = {r.ticker for r in await PriceWatchlistRepository(session).list_enabled()}
            position_tickers = {r.ticker for r in await PositionRepository(session).list_all_open()}
            users = [
                u
                for u in await UserRepository(session).get_all()
                if u.role == Role.trader.value and u.is_active
            ]
            strat_service = self.ctx.strategy_service(session)
            discovery_sources: dict[int, list[str]] = {}
            for user in users:
                try:
                    values = await self.ctx.config_service(session).compile_values(
                        user_id=user.id, asset_class="equity"
                    )
                except Exception:  # noqa: BLE001 - one bad user's config must not block the fetch
                    continue
                buy = strat_service.get_active(values, "buy")
                if buy is not None and not buy.uses_watchlist:
                    discovery_sources[user.id] = buy.external_sources

        discovery_tickers: set[str] = set()
        for user_id, sources in discovery_sources.items():
            candidates = await self._discover_buy_candidates(user_id, sources)
            discovery_tickers.update(candidates.keys())

        return sorted(watchlist_tickers | position_tickers | discovery_tickers)

    async def _watchlist_by_poll_interval(self, poll_interval: str) -> list[str]:
        """Enabled watchlist tickers set (Settings > Price > Watchlist) to this
        intraday granularity — "1m" (green chip) or "1h" (blue chip, the default).
        Independent of the always-on daily ("1d") fetch every watchlist ticker gets
        via ._watchlist() above regardless of this per-ticker choice. When
        ``schedule.market_hours_enabled`` is on (the default), a ticker whose
        region's market is currently closed (see market_hours.is_open) is skipped
        until its session reopens.

        An open position that isn't on the watchlist at all (e.g. removed after
        buying) still needs intraday updates to catch an intraday stop/tier cross
        (bugs.md finding 3) — it's defaulted to the "1h" granularity here, since it
        has no per-ticker chip choice of its own to read.
        """
        async with self.ctx.db.session() as session:
            rows = await PriceWatchlistRepository(session).list_enabled()
            position_tickers = {r.ticker for r in await PositionRepository(session).list_all_open()}
        gate_enabled = self.ctx.settings.schedule.market_hours_enabled
        watchlist_tickers = {r.ticker for r in rows}
        selected = {r.ticker: r.region for r in rows if r.poll_interval == poll_interval}
        if poll_interval == "1h":
            for ticker in position_tickers - watchlist_tickers:
                selected.setdefault(ticker, market_hours.US)
        return [
            ticker
            for ticker, region in selected.items()
            if not gate_enabled or market_hours.is_open(region)
        ]

    async def _mark_fetched(self, ticker: str, interval: str, rows: int, duration: float) -> None:
        async with self.ctx.db.transaction() as session:
            await PriceFetchLogRepository(session).mark_fetched(ticker, interval)
            await PriceFetchAttemptRepository(session).record(
                ticker=ticker,
                interval=interval,
                status="success",
                duration_seconds=duration,
                rows_fetched=rows,
            )

    async def _mark_fetch_error(self, ticker: str, interval: str, message: str, duration: float) -> None:
        async with self.ctx.db.transaction() as session:
            await PriceFetchAttemptRepository(session).record(
                ticker=ticker,
                interval=interval,
                status="error",
                duration_seconds=duration,
                error_message=message,
            )

    def _pipeline(self) -> PricePipeline:
        return PricePipeline(
            storage_path=self.ctx.settings.price.storage_path,
            fetcher=yahoofinance.fetch_ohlcv,
            watchlist_provider=self._watchlist,
            bus=self.ctx.bus,
            on_fetched=self._mark_fetched,
            on_error=self._mark_fetch_error,
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
            on_error=self._mark_fetch_error,
        )

    async def run_strategies(self) -> None:
        """Run each trader's active sell strategy over their own open positions, and
        their active buy strategy over its candidate tickers.

        Sell strategies only ever need to look at what a user already holds
        (``PositionRepository.list_all_open`` — a position is itself the
        "universe", nothing extra to configure). Buy strategies need a candidate
        list from somewhere, and get it one of two ways depending on
        ``LoadedStrategy.uses_watchlist``: the default (True, e.g. ``trend_follow``)
        evaluates the shared, user-curated price watchlist (Prices page > Watchlist
        / ``GET-POST-PATCH-DELETE /api/v1/prices/watchlist``); a strategy that sets
        ``USES_WATCHLIST = False`` (e.g. ``signal_follow``) instead discovers its own
        candidates directly from its declared ``EXTERNAL_SOURCES`` (see
        ``SignalSourceRegistry.discover`` in src/modules/signal/sources.py) and never
        touches the watchlist at all.
        """
        async with self.ctx.db.session() as session:
            users = [
                u
                for u in await UserRepository(session).get_all()
                if u.role == Role.trader.value and u.is_active
            ]
            watchlist = await PriceWatchlistRepository(session).list_enabled()
            region_by_ticker = {
                r.ticker: r.region for r in await PriceWatchlistRepository(session).list_all()
            }
            strat_service = self.ctx.strategy_service(session)

        market_hours_enabled = self.ctx.settings.schedule.market_hours_enabled

        def _region_open(ticker: str) -> bool:
            if not market_hours_enabled:
                return True
            return market_hours.is_open(region_by_ticker.get(ticker, market_hours.US))

        _logger.debug(
            "run_strategies: %d trader(s), %d enabled watchlist ticker(s): %s",
            len(users),
            len(watchlist),
            [w.ticker for w in watchlist],
        )
        if not watchlist:
            _logger.debug(
                "run_strategies: watchlist is empty — a watchlist-based buy strategy "
                "(LoadedStrategy.uses_watchlist=True, e.g. trend_follow) will never "
                "produce a signal until a candidate ticker is added (Prices page > "
                "Watchlist); a strategy that discovers its own candidates instead "
                "(uses_watchlist=False, e.g. signal_follow) is unaffected, and sell "
                "strategies always run over open positions regardless"
            )

        storage_path = self.ctx.settings.price.storage_path
        # Loaded once per run, not per (user, ticker) — a strategy that wants
        # market-regime context (see src/modules/price/regime.py) reads this via
        # StrategyContext.benchmark_data rather than fetching it itself.
        benchmark_data = storage.read_bars(storage_path, self.ctx.settings.price.benchmark_ticker, "1d")
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
                    if not _region_open(position.ticker):
                        _logger.debug(
                            "run_strategies: %s's market is currently closed — skipping sell eval",
                            position.ticker,
                        )
                        continue
                    df = storage.read_bars(storage_path, position.ticker, "1d")
                    if df is None or df.empty:
                        _logger.debug(
                            "run_strategies: no stored bars for held position %s — skipping "
                            "(it stays queued for the next price fetch, see ._watchlist)",
                            position.ticker,
                        )
                        continue
                    try:
                        await self._evaluate_sell(user.id, position, df, values, sell, benchmark_data)
                    except Exception as exc:  # noqa: BLE001
                        _logger.warning("sell strategy eval failed %s/%s: %s", user.id, position.ticker, exc)

            if buy is not None:
                if buy.uses_watchlist:
                    for item in watchlist:
                        if not _region_open(item.ticker):
                            _logger.debug(
                                "run_strategies: %s's market is currently closed — skipping buy eval",
                                item.ticker,
                            )
                            continue
                        # Bars are only a *requirement* for a buy strategy that
                        # actually consumes context.price_data (e.g. trend_follow's
                        # local SMA/RSI, which needs 200+ days of history) — a
                        # strategy that decides purely from external signal sources
                        # needs no locally-stored history at all, so evaluation is
                        # never skipped here just because storage.read_bars() came
                        # back empty/None. Each strategy is responsible for saying
                        # so in its own reasoning if it does need bars it doesn't
                        # have yet (see trend_follow's "only N bars stored" check).
                        df = storage.read_bars(storage_path, item.ticker, "1d")
                        try:
                            await self._evaluate_buy(user.id, item, df, values, buy, benchmark_data)
                        except Exception as exc:  # noqa: BLE001
                            _logger.warning(
                                "buy strategy eval failed %s/%s: %s", user.id, item.ticker, exc
                            )
                else:
                    # This buy strategy discovers its own candidate tickers (e.g.
                    # signal_follow, USES_WATCHLIST = False) instead of using the
                    # shared price watchlist at all.
                    await self._evaluate_buy_by_discovery(user.id, buy, values, benchmark_data, _region_open)

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

    async def _discover_buy_candidates(
        self, user_id: int, sources: list[str]
    ) -> dict[str, list[ExternalSignal]]:
        """Every ticker any of ``sources`` currently has an opinion on, grouped by
        ticker — the discovery counterpart to ``_external_signals`` above, used by a
        buy strategy that sets ``USES_WATCHLIST = False`` (see
        ``SignalSourceRegistry.discover`` in src/modules/signal/sources.py). Never
        raises: a source that's unconfigured or fails simply contributes nothing."""
        if not sources:
            return {}
        try:
            async with self.ctx.db.session() as session:
                registry = SignalSourceRegistry(self.ctx.credential_manager(session), user_id=user_id)
                signals = await registry.discover(sources)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("external signal discovery failed for user %s: %s", user_id, exc)
            return {}
        by_ticker: dict[str, list[ExternalSignal]] = {}
        for sig in signals:
            by_ticker.setdefault(sig.ticker, []).append(sig)
        return by_ticker

    async def _evaluate_buy_by_discovery(
        self, user_id: int, buy: LoadedStrategy, values, benchmark_data, region_open
    ) -> None:
        candidates = await self._discover_buy_candidates(user_id, buy.external_sources)
        _logger.debug(
            "run_strategies: %s discovered %d candidate ticker(s) from %s: %s",
            buy.name,
            len(candidates),
            buy.external_sources,
            sorted(candidates),
        )
        storage_path = self.ctx.settings.price.storage_path
        for ticker, signals in candidates.items():
            if not region_open(ticker):
                _logger.debug(
                    "run_strategies: %s's market is currently closed — skipping buy eval", ticker
                )
                continue
            df = storage.read_bars(storage_path, ticker, "1d")
            item = _DiscoveredCandidate(ticker=ticker)
            try:
                await self._evaluate_buy(
                    user_id, item, df, values, buy, benchmark_data, external_signals=signals
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("buy strategy eval failed %s/%s: %s", user_id, ticker, exc)

    async def _evaluate_sell(
        self, user_id: int, position, df, values, sell: LoadedStrategy, benchmark_data=None
    ) -> None:
        external = await self._external_signals(user_id, position.ticker, sell.external_sources)
        current_price = storage.latest_price(self.ctx.settings.price.storage_path, position.ticker)
        high_water_mark = position.high_water_mark
        if current_price is not None:
            # Refetch by id rather than reusing `position` (loaded on a session that's
            # already closed by the time we get here) — bump_high_water_mark writes,
            # and a detached cross-session ORM object must never be passed into a
            # repository write (see docs/agent-notes.md cross-session gotcha).
            async with self.ctx.db.transaction() as session:
                fresh = await PositionRepository(session).get_by_id(position.id)
                if fresh is not None:
                    updated = await PositionRepository(session).bump_high_water_mark(fresh, current_price)
                    high_water_mark = updated.high_water_mark
        sell_decision = await sell.run(
            StrategyContext(
                ticker=position.ticker,
                user_id=user_id,
                asset_class=position.asset_class,
                config=values,
                price_data=df,
                current_price=current_price,
                position=PositionView(
                    position.ticker,
                    position.quantity,
                    position.avg_price,
                    tier1_taken=position.profit_tier1_taken,
                    tier2_taken=position.profit_tier2_taken,
                    high_water_mark=high_water_mark,
                ),
                external_signals=external,
                benchmark_data=benchmark_data,
            )
        )
        await self._record_decision(user_id, position, sell.name, "sell", sell_decision)
        if sell_decision.acted and sell_decision.event is not None:
            _logger.debug("run_strategies: %s sell signal for %s", sell.name, position.ticker)
            await self.ctx.bus.publish(sell_decision.event)

    async def _evaluate_buy(
        self,
        user_id: int,
        item,
        df,
        values,
        buy: LoadedStrategy,
        benchmark_data=None,
        external_signals: list[ExternalSignal] | None = None,
    ) -> None:
        # The discovery path (_evaluate_buy_by_discovery) already fetched every
        # candidate's signals as part of discovering it — pass those straight
        # through instead of re-fetching per-ticker (that fetch is per-ticker,
        # discovery is bulk-per-source; redoing it here would double the network
        # calls for no reason).
        external = (
            external_signals
            if external_signals is not None
            else await self._external_signals(user_id, item.ticker, buy.external_sources)
        )
        current_price = storage.latest_price(self.ctx.settings.price.storage_path, item.ticker)
        buy_decision = await buy.run(
            StrategyContext(
                ticker=item.ticker,
                user_id=user_id,
                asset_class=item.asset_class,
                config=values,
                price_data=df,
                current_price=current_price,
                external_signals=external,
                benchmark_data=benchmark_data,
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
        self.scheduler.add_interval_job(
            self.execution.reconcile_pending_orders,
            id="reconcile_orders",
            seconds=max(10, schedule.reconcile_orders_seconds),
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
