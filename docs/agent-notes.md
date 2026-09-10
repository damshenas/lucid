# Agent notes

Accumulated bug-fix / architecture notes from past AI-assisted sessions on this
repo. Kept in-repo (not in any external/agent memory store) so the history stays
with the codebase. Newest entries at the bottom.

- Testing: NEVER run pytest/npm locally. Test via `docker build -f docker/Dockerfile
  -t lucid-test .` from repo root — the Dockerfile's `RUN python -m pytest -q` step
  runs the full backend suite, and the earlier `npm run build` UI stage validates the
  frontend. Build failure = test failure. (Enforced by
  .github/instructions/generic.instructions.md.) This is Docker-only with NO
  exceptions — never run `python3 -c "..."` or any other code locally even for a
  throwaway check (e.g. verifying a date's weekday or timezone math for a test).
  If unsure about such a fact, write the test and let the Docker pytest run be the
  verification; fix based on its failure output.
- FastAPI gotcha: `get_current_user` / `require_permission(...)` (src/api/deps.py)
  load the `User` on their OWN short-lived DB session, separate from the `session:
  AsyncSession = Depends(get_session)` used in the route body. Never pass that `user`
  object into `SomeRepository(session).update(user, ...)` — it raises
  `sqlalchemy.exc.InvalidRequestError: not persistent within this Session`. Always
  refetch: `stored = await UserRepository(session).get_by_id(user.id)` then update
  `stored` (see src/api/v1/auth.py change_password for the reference pattern).
- `src/modules/db/repositories/__init__.py` and `src/modules/db/models/__init__.py`
  are both barrel files that re-export every repo/model — when deleting a
  model/repository, grep both files (easy to miss, caused a docker build failure once).
- UI: `npm run build` in the Dockerfile is just `vite build` — no `tsc` type-check
  gate, so unused imports/vars don't fail the build (tsconfig has noUnusedLocals but
  it's never enforced by the pipeline). Still keep imports clean by habit.
- Backend: `python -m pytest -q` in the Dockerfile is the only backend gate — no
  ruff/lint step either.
- Config schema (`src/modules/configs/__init__.py` `_model_fields`/`module_sections`)
  drives Settings UI form fields from `src/conf/schema.py` Pydantic models. Enum
  fields get a `choices` list in the compiled schema; frontend's SchemaGroup.tsx
  renders those as a `<Select>` instead of free text.
- Strategy files (`strategies/{buy,sell}/*.py`) can declare an optional
  module-level `FEATURES: list[str]` (read in `src/modules/strategy/loader.py`,
  persisted via `StrategyRegistry.features` JSON column, migration 0004) — this is
  how the per-active-strategy sidebar page (`pages/StrategyDetail.tsx`) decides
  what extra info to show (e.g. `trend_follow` declares `["signals"]`).
- `NAV_ITEMS` (lib/nav.ts) is now merged at runtime in AppLayout.tsx with dynamic
  per-active-strategy entries (`hooks/useActiveStrategies.ts`, path
  `/strategy/:name`) — static array isn't the full nav list anymore.
- Buy vs sell strategies use *different* ticker sources in `TradingRuntime.
  run_strategies` (src/api/runtime.py) — fixed from an earlier bug where sell was also
  gated on the watchlist: **sell** strategies run over `PositionRepository.
  list_all_open()` (every user's open positions, regardless of watchlist); **buy**
  strategies run over the *global* `price_watchlist` table (enabled=True) since a buy
  needs a user-curated candidate universe. `_watchlist()` (the price-fetch pipeline's
  ticker source) is watchlist ∪ every open-position ticker, so a held position keeps
  getting fresh bars even if removed from the watchlist. Watchlist itself is managed
  via GET/POST/PATCH/DELETE `/api/v1/prices/watchlist` and the Prices page's
  "Watchlist" card — permission `edit_own_strategies` to mutate, any authenticated
  user to view.
- Price storage layout is `<price.storage_path>/<interval>/<TICKER>.parquet`
  (src/modules/price/storage.py) — interval is a free string like `"1d"`/`"15m"`, NOT
  a fixed enum. This repo's pipeline has *never* used folder names like `ohlcv/`,
  `ohlcv_1m/`, or `indicators/` (checked full git history) — if those exist under
  `/data/prices/` in a deployment, they're leftovers from a different/legacy
  pipeline sharing the volume and are invisible to `GET /api/v1/prices/{ticker}`
  (404) until migrated. Use `python -m src.scripts.migrate_legacy_prices
  <legacy_dir> <storage_path> <interval>` (new script, tested in tests/test_price.py)
  to copy them into the current layout — never overwrites, merges via
  `storage.append_bars`.
- External signal sources (finviz/tradingview/zacks/barchart — src/modules/com/*)
  existed only as unwired HTTP-client stubs (hit a generic `/quote/{ticker}`-style
  REST shape, never called by anything, only unit-tested with mocked transports) —
  no strategy or runtime code ever invoked them. Added
  `src/modules/signal/sources.py` (`SignalSourceRegistry`/`ExternalSignal`) to
  normalize each into buy/sell/hold, gated on `<source>_base_url`/`_api_key`
  credentials (added to `CREDENTIAL_CATALOG` in api/v1/credentials.py). A strategy
  opts in via an optional `EXTERNAL_SOURCES: list[str]` module attribute (mirrors
  `FEATURES`, read in `src/modules/strategy/loader.py` into `LoadedStrategy.
  external_sources`); `TradingRuntime._external_signals` fetches only what's declared
  and hands results to `StrategyContext.external_signals` /
  `.external_signal(name)`. Manual test/check: `GET /api/v1/signals/sources`,
  `POST /api/v1/signals/sources/check`.
- `strategies/README.md` is now the canonical strategy-authoring reference (kept in
  sync with the shorter `docs/strategies.md`) — read it before adding/modifying a
  buy/sell strategy file.
- Watchlist management moved from the Prices page into Settings > Price > Watchlist
  (pages/settings/WatchlistTab.tsx) — redesigned as a chip list (not one row per
  ticker), filterable by asset class (nested `Tabs`, one per `ASSET_CLASSES` value +
  "All"). Each ticker now also carries a per-ticker intraday granularity,
  `PriceWatchlist.poll_interval` ("1m" green chip / "1h" blue chip, default "1h",
  migration 0006, CHECK-constrained) — click a chip to toggle it. `PriceConfig.
  intraday_interval` (the old single global bar interval) was removed since
  granularity is per-ticker now; `TradingRuntime.register_jobs` runs two separate
  intraday jobs (`price_intraday_1m`/`price_intraday_1h`), each with its own
  `PricePipeline` whose `watchlist_provider` is
  `_watchlist_by_poll_interval("1m"|"1h")` — daily ("1d") fetch is unaffected, still
  every watchlist ticker ∪ open positions regardless of poll_interval.
  Edits in `WatchlistTab` are local "draft" state only (add/remove/toggle-color) —
  nothing hits the backend until Settings' single page-level bottom "Save changes"
  button is clicked. `hooks/useUnsavedChangesGuard.ts` (called once in Settings.tsx,
  combining `edited` (schema fields) + `watchlistDraft.dirty`) warns before a tab
  close/reload or in-app link click while dirty (this app uses a plain
  `<BrowserRouter>/<Routes>`, not a data router, so react-router's `useBlocker` isn't
  available — the guard intercepts capture-phase `<a>` clicks instead). This hook is
  general-purpose, reusable for any future unsaved-draft UI.
- Watchlist state/logic lives in `hooks/useWatchlistDraft.ts` (not owned by
  `WatchlistTab`, which is now purely presentational) specifically so Settings.tsx's
  *one* bottom Save button can commit both schema-field edits and watchlist changes
  together — there is deliberately no separate per-tab Save/Discard button anywhere
  in Settings.
- CRITICAL bug fixed: `GET /api/v1/prices/watchlist` returns real watchlist rows
  *plus* synthetic "ghost" entries for any ticker that merely has stored price bars
  on disk but was never actually added (e.g. an ad-hoc backfill, or the
  migrate_legacy_prices script) — originally added only to power the Prices page's
  ticker `<datalist>` autocomplete. The new Watchlist chip UI couldn't tell these
  apart from real entries, so toggling a ghost ticker (e.g. AMZN right after the
  legacy-price migration) and clicking Save 404'd
  (`PATCH .../watchlist/AMZN` → `'AMZN' is not on the watchlist`) since it was never
  really added. Fixed by adding `on_watchlist: bool` to each row in that response
  (`true` only for actual `price_watchlist` table rows); `useWatchlistDraft`'s
  `toDraft()` filters to `on_watchlist === true` before building draft/saved state,
  so a ghost entry is simply invisible to the editable UI until it's genuinely
  POSTed via "Add ticker". Regression test:
  `test_watchlist_disk_only_tickers_are_not_editable` in tests/test_api.py.
- Logging: `LOG_LEVEL` env var (see docker/compose.yml) always wins over the DB
  `logger.level` setting (intentional ops override, src/api/main.py). When unset,
  `src/api/v1/settings.py` save_values now calls `src.modules.logger.set_level()`
  live so a Settings change takes effect without a restart (previously it silently
  did nothing — `configure_logging` only ran once at startup).
- `strategy_scan_hour` / the periodic daily "strategy_scan" cron job was removed
  (src/api/runtime.py register_jobs) — strategy files are (re)scanned only at
  startup and via manual `POST /api/v1/strategies/scan`.
- CRITICAL bug fixed: `ExecutionEngine.handle_buy`/`handle_sell` (src/modules/execution/__init__.py)
  never called `SignalService.store_from_event()` — the `signals` table was NEVER
  populated at runtime (only in tests), no matter how many strategies fired. Fixed by
  storing the signal in its own committed transaction up front, then
  mark_acted/mark_blocked (with a reason) in a second transaction — never reuse a
  Signal ORM object across `db.transaction()` blocks, always refetch by id
  (`SignalRepository(session).get_by_id(signal_id)`) per the cross-session gotcha above.
- Strategy `run()` contract changed: now returns `StrategyDecision` (src/modules/strategy/context.py:
  `acted: bool`, `reasoning: str`, `event: BuySignalEvent|SellSignalEvent|None`) instead of
  bare `Event | None` — every branch must explain itself, not just the acted case. This
  feeds `strategy_decisions` table (src/modules/db/models/decision.py) via
  `TradingRuntime._record_decision` (src/api/runtime.py), deduped so it only inserts a
  new row when the (acted, reasoning) tuple actually changes for that (user, ticker,
  strategy) — otherwise a static condition would spam a row every poll interval forever.
- Frontend session-expiry: `lib/sessionExpiry.ts` (same useSyncExternalStore pub/sub
  pattern as lib/serverStatus.ts) + api/client.ts's request() marks it on any 401 from
  a request that *had* a token attached (not a bare login attempt) — hooks/useAuth.ts
  subscribes and forces `token` back to null, kicking the user back to Login with a
  "session expired" banner from anywhere in the app.
- Added `POST /api/v1/admin/reset-trading-data` (admin-only, new `Permission.
  manage_trading_data`) — danger-zone "start fresh" reset: hard-deletes a trader's
  (or every trader's, if `user_id` omitted) positions/orders/signals/signal_outcomes/
  strategy_decisions via new `delete_all_for_user()` methods on those repos (bulk
  `sqlalchemy.delete()`, since sqlite in tests has no FK-cascade enforcement — never
  rely on model-level `ondelete=` alone for a wipe). Never touches users, credentials,
  watchlist, or config/settings. When `sync_from_broker` (default True) it re-syncs
  positions from the broker right after, via `sync_positions_from_broker()` (factored
  out of `src/api/v1/positions.py`'s `POST /positions/sync` so both share the same
  reconciliation code). UI: a "Reset trading data" icon button per trader row in
  Users.tsx (admin-only page). Test:
  `test_admin_reset_trading_data_wipes_history_and_resyncs` in tests/test_api.py.
- FIXED bug: `configure_logging()` (src/modules/logger/__init__.py) had an
  `if _configured: return` guard covering BOTH handler setup and the level. Many
  modules do a module-level `_logger = get_logger("name")` (bus, execution,
  schedules, com/*, etc.) which runs at **import** time — i.e. while `src.api.main`
  is still being imported, well before its `_lifespan` calls
  `configure_logging(level=os.environ.get("LOG_LEVEL", ctx.settings.logger.level))`.
  `get_logger()` calls `configure_logging()` with its default `level="INFO"` if not
  yet configured, so that implicit call always wins and locks the whole process at
  INFO forever — the real, later call from `_lifespan` (and thus `LOG_LEVEL`/
  `logger.level`) was a **silent no-op**, even though `docker/compose.yml` already
  hardcodes `LOG_LEVEL: debug`. This is why debug logs (e.g.
  `TradingRuntime.run_strategies`'s skip-reason `_logger.debug(...)` calls) never
  appeared, and why changing `logger.level` in the Settings UI appeared to do
  nothing. Fix: split the guard — handler/formatter setup stays one-time, but
  `root.setLevel(...)` now runs on every call. Regression test:
  `test_configure_logging_applies_level_even_after_handlers_already_set_up` in
  tests/test_api.py. General lesson: an "idempotent configure" function must not
  gate mutable *state* (like log level) behind the same one-time flag as one-time
  *setup* (like handler registration) if anything else in the codebase can trigger
  an earlier implicit call with different/default arguments.
- Added `strategies/buy/signal_follow.py`: a built-in buy strategy that decides
  purely from external signal-provider ratings (`EXTERNAL_SOURCES = ["finviz",
  "tradingview", "zacks", "barchart"]`) and never reads `context.price_data` at all —
  unlike `trend_follow` (local SMA50/SMA200/RSI, needs 200+ days of stored daily
  bars before it can say anything). `CONFIG_SCHEMA.min_buy_votes` (default 1) is how
  many *answered* sources (error is None) must rate "buy" to act.
- FIXED bug/gap: `TradingRuntime.run_strategies`'s buy loop (src/api/runtime.py)
  used to `continue` (skip the strategy entirely, no decision ever recorded) for any
  watchlist ticker with zero stored price bars — this blocked ALL buy strategies
  equally, even one like `signal_follow` that never needs bars. Now `df` (possibly
  `None`) is always passed through to `_evaluate_buy`; each strategy decides for
  itself whether it needs bars (`trend_follow` already handles `price_data=None`
  gracefully). The **sell** loop's bar-required skip is intentionally unchanged —
  a sell strategy always needs a current price to evaluate a position.
  IMPORTANT: this only changes *strategy evaluation*, not *execution* —
  `ExecutionEngine.handle_buy` (src/modules/execution/__init__.py) independently
  blocks any buy with `price <= 0` ("no price", via `_quote()` reading the latest
  stored daily close) — so a signal_follow buy on a ticker with literally zero
  fetched bars will still be correctly rejected at execution time until at least one
  bar exists (which happens automatically since watchlist tickers are already in the
  price-fetch pipeline's ticker set, see `_watchlist()`).
- The watchlist (`price_watchlist` table/UI) was deliberately NOT removed despite an
  initial user request to eliminate it — after clarifying, the user confirmed:
  (a) buy-candidate *discovery* should come from external signal sources, not local
  technical indicators, but (b) price-fetch scope should still be "open positions
  AND watchlist" (unchanged), since the watchlist still serves as the required
  candidate-ticker list for *any* buy strategy (scanning the whole market isn't
  practical — rate limits/cost) and as a pure price-tracking list independent of
  buying. Don't attempt to remove the watchlist again without re-confirming — it was
  a considered decision, not an oversight.
- FIXED prod-only bug: `strategy_decisions` table (migration 0005) was hand-written
  instead of generated from ORM metadata (unlike 0001's `Base.metadata.create_all`)
  and its `created_at`/`updated_at` columns were `nullable=False` with NO
  `server_default` — unlike `TimestampMixin` (server_default=func.now()) and unlike
  every other table. Any `StrategyDecisionRepository.create()` (i.e. every recorded
  strategy decision) raised `NotNullViolationError` in real Postgres. Tests never
  caught this because tests/conftest.py builds its sqlite schema straight from
  `Base.metadata` (correct defaults baked in), never by actually running Alembic
  migrations — this class of drift (hand-written migration vs. ORM model) is
  invisible to the whole test suite. Fixed via a new migration
  (0011_strategy_decisions_timestamp_defaults.py, `ALTER COLUMN ... SET DEFAULT
  now()`) — MUST run `alembic upgrade head` against the real deployed Postgres for
  this to take effect; the sqlite-based pytest suite can't validate it. General
  lesson: whenever hand-writing an Alembic migration (vs. autogenerate) for a model
  using `TimestampMixin`, double check `server_default=sa.text("now()")` is on both
  created_at and updated_at, and diff against how `TimestampMixin` actually declares
  them — grep other migrations' `op.create_table` calls to compare.
- Activating a buy/sell strategy now triggers an immediate background
  `TradingRuntime.run_strategies()` pass (via `BackgroundTasks`) instead of waiting
  up to `schedule.poll_positions_seconds` for the next scheduled tick — wired into
  both places a strategy can be activated: `POST /api/v1/settings` (save_values,
  when `strategy.active_{buy,sell}_strategy` is in the saved keys — this is what the
  Settings > Strategy UI actually uses) and `PATCH /api/v1/strategies/{name}/
  activate` (the standalone endpoint, not currently called by the UI but still a
  valid API entry point / used directly by tests).
- FIXED bug: [Login.tsx](../src/ui/src/pages/Login.tsx) "need to click Sign in twice"
  — the form's `username`/`password` were plain React-controlled state, read by
  `submit()` on click. Some browsers' autofill / password-manager extensions set an
  `<input>`'s DOM value without dispatching a React-visible input/change event, so
  the state stayed empty on the very first submit (rejected as blank credentials)
  even though the field visibly showed the autofilled text — a second click (after
  some later event synced the state) then worked. Fixed by reading submitted values
  straight from `new FormData(e.currentTarget)` in the submit handler instead of
  trusting the controlled state — general pattern worth reusing for any other
  autofill-prone form (e.g. change-password) if the same complaint recurs.
- The watchlist (`price_watchlist` table/UI) still exists and is still required for
  watchlist-based buy strategies (`trend_follow`, any custom strategy that doesn't
  opt out) — but `signal_follow` was later changed (2026-07-20, explicit user
  directive: "must not depend on the watchlist. period.") to NOT use it at all.
  `LoadedStrategy.uses_watchlist` (src/modules/strategy/loader.py, from an optional
  module-level `USES_WATCHLIST` attribute, default `True`) controls this per buy
  strategy. When `False`, `TradingRuntime.run_strategies` (src/api/runtime.py) skips
  the watchlist loop entirely for that strategy and instead calls
  `_evaluate_buy_by_discovery`, which calls the NEW `SignalSourceRegistry.discover()`
  (src/modules/signal/sources.py) — one bulk call per source (not per ticker) via
  each connector's new discovery method (`ZacksConnector.fetch_ranks`,
  `FinvizConnector.fetch_screener`, `TradingViewConnector.fetch_all_technicals`,
  `BarchartConnector.fetch_all_opinions`, each hitting a new list-style endpoint —
  `/ranks`, `/screener`, `/technicals`, `/opinions` respectively, returning
  `{"items": [...]}` shaped like the existing per-ticker methods' results) —
  aggregates every ticker any declared source currently has an opinion on, then
  evaluates `run()` once per discovered ticker (no watchlist row needed at all;
  `_DiscoveredCandidate` stands in for the usual PriceWatchlist/Position "item").
  `signal_follow`'s `min_buy_votes` default was bumped 1 -> 2 per the same directive
  ("if you see a signal from 2 different sources, execute"). IMPORTANT: this is a
  *contract Lucid invented* for the external services behind `<source>_base_url` —
  those are the user's own infrastructure; if their actual backend doesn't implement
  a `/ranks`/`/screener`/`/technicals`/`/opinions` list endpoint yet, discovery will
  just log a warning and contribute nothing for that source (never raises/breaks the
  run) until it does.
- FIXED architecture mismatch (2026-07-20, user pointed at a sibling legacy
  `dealer` app's `integration/web` directory): the original
  finviz/tradingview/zacks/barchart connectors were invented — they assumed a
  generic per-ticker JSON REST API behind a user-configurable `<source>_base_url`/
  `_api_key`, which doesn't match the real legacy `dealer` app at all. The actual
  old code: (1) needs **zero credentials** — hits fixed public endpoints directly;
  (2) is **screener/discovery-shaped**, not per-ticker (finviz scrapes
  finviz.com's public screener HTML pages via BeautifulSoup/table-parsing;
  tradingview POSTs to TradingView's real undocumented public scanner endpoint
  `https://scanner.tradingview.com/america/scan`, clean JSON, pre-filtered
  server-side to `Recommend.All > 0.3`; zacks scrapes zacks.com behind
  Cloudflare/Incapsula, needing a **Playwright headless browser** to reliably
  bypass anti-bot; barchart hits an internal JSON API via a scraped session/XSRF
  cookie dance, with a Playwright HTML fallback); (3) caches results ~30min
  (`integration/web/cache.py` `ScraperCache`) and retries via `tenacity`.
  Decision (explicit user choice, confirmed via follow-up): implement **finviz**
  (real HTML scrape, simplified to a `quote.ashx?t=TICKER` regex link-scan rather
  than the old fragile table/column parser — no bs4 dependency needed) and
  **tradingview** (real scanner POST, faithfully ported) for real; **zacks** and
  **barchart** became explicit `DISABLED` placeholders (same pattern as
  `com/telegram`/`.claude` — raise `DisabledConnectorError`), NOT wired into
  `signal/sources.py` `_SOURCES`/`SOURCE_NAMES` at all (not just "unconfigured").
  Playwright was NOT added (would need chromium in the Docker image).
  `_Source` (signal/sources.py) gained `requires_credentials: bool = False` so
  `SignalSourceRegistry` can skip the whole credential-lookup path for a
  credential-free source (both currently wired ones) while still supporting a
  future authenticated source — `source_requires_credentials(name)` is used by
  `GET /api/v1/signals/sources` so these correctly report `configured: true`
  always. Removed all 8 finviz/tradingview/zacks/barchart `base_url`/`api_key`
  entries from `CREDENTIAL_CATALOG` (src/api/v1/credentials.py) — nothing to
  configure for any of the four anymore. `signal_follow.EXTERNAL_SOURCES` is now
  `["finviz", "tradingview"]` only (was 4 sources) — `min_buy_votes=2` (unchanged)
  now means "both of the two wired sources must agree", still matching the
  original "2 different sources" directive. Legal/ToS note flagged to the user:
  scraping finviz.com (and zacks.com/barchart.com, if ever re-enabled) may violate
  those sites' Terms of Service — that's a knowing call on their part, not
  something to silently carry over.
- FIXED the REAL "login needs 2 clicks" bug (2026-07-20, the earlier FormData/autofill
  fix in Login.tsx was a real fix for a different symptom but did NOT solve this — user
  reported it was still happening). Root cause: `lib/sessionExpiry.ts`'s
  `markSessionExpired()`/`clearSessionExpired()` both call the exact same listener set
  with no "direction" info. `useAuth.ts`'s `subscribeSessionExpiry` callback naively
  assumed every notification meant "force logout" (`setTokenState(null);
  setSessionExpired(true)`), including when `clearSessionExpired()` fires (called at
  the end of every successful `login()`/`setup()`). Repro: any time a token in
  localStorage is already stale (e.g. the very common case of the 30min access-token
  natural expiry, or a stale token from before a container restart) — `expired` module
  flag is `true`. On the NEXT login: `api.login()` succeeds, `setTokenState(freshToken)`
  runs, then `clearSessionExpired()` (expired was true -> now false) notifies listeners
  -> the useAuth listener clobbers `tokenState` back to `null` in the same tick. First
  click "does nothing" (silently reverts, no thrown error so no red error banner —
  though `sessionExpired` React state does get set true, showing the informational cyan
  "session expired" banner, which the user didn't initially register as "an error").
  Second click: `expired` is already `false`, so `clearSessionExpired()` is a no-op ->
  nothing clobbers the fresh login -> succeeds. FIX: the listener in useAuth.ts now
  re-checks `isSessionExpired()` itself and only reacts when actually true (new export
  added to sessionExpiry.ts's public API — it already existed, just wasn't imported/used
  by useAuth). General lesson: a pub/sub store with only ONE listener signature and TWO
  possible state transitions (set vs clear) must let subscribers distinguish which
  transition occurred (either via an argument, or by re-querying the authoritative flag
  inside the callback) — never assume "notified" == "the thing became true".
- Added standard 5-level rating system (`strong_buy`/`buy`/`neutral`/`sell`/`strong_sell`,
  TradingView-style thresholds) in NEW `src/modules/signal/rating.py`
  (`rating_from_score`, `rating_from_text`, `rating_from_vote_counts`,
  `direction_from_rating`) plus two NEW real connectors: `src/modules/com/finnhub`
  (Recommendation Trends, `GET /stock/recommendation?symbol=`, per-ticker only, no
  discovery/bulk method) and `src/modules/com/fmp` (`ratings-snapshot` — `overallScore`
  1-5 quintile, 5=best; `grades-consensus` — strongBuy/buy/hold/sell/strongSell vote
  counts; both under `https://financialmodelingprep.com/stable`). Both connectors are
  **keyword-only constructors** (`__init__(self, *, api_key: str, ...)`, no positional
  `base_url` — unlike finviz/tradingview which take positional `base_url`) since they
  hit a fixed public base URL, only the API key is user-specific.
  `_Source` (signal/sources.py) gained `to_rating` (renamed from `to_direction`),
  optional `discover_method: str | None` (None for finnhub/fmp — no bulk endpoint),
  `needs_base_url: bool` (False for finnhub/fmp), `credential_prefix: str | None`
  (lets `fmp_rating`/`fmp_grades` both resolve `fmp_api_key`, not
  `fmp_rating_api_key`/`fmp_grades_api_key`). `ExternalSignal` gained a `rating`
  field alongside `direction` (rating is the raw 5-level bucket; direction is the
  buy/hold/sell collapse via `direction_from_rating`). `CREDENTIAL_CATALOG` gained
  `finnhub_api_key`/`fmp_api_key`. `SOURCE_NAMES` is now 5 entries: tradingview,
  finviz, finnhub, fmp_rating, fmp_grades. Zacks/Barchart remain intentionally
  DISABLED, not wired in. When renaming a `_Source` dataclass field used across
  `_build_connector`/`_discover_one`/`_fetch_one`, must update all three methods in
  the same file — easy to leave half-applied via block-by-block edits; always
  re-`read_file`/`get_errors` the whole file after a multi-edit before considering
  it done. FMP's `ratings-snapshot` "stable" endpoint has NO plain-English
  recommendation text field (only `overallScore` int 1-5) — schema confirmed via
  scraping FMP's public docs *pages* (not live API calls; the `demo` key 401s on
  stable endpoints), same technique used for Finnhub's docs page.
- FIXED bug (2026-08-20): `sync_positions_from_broker` (src/api/v1/positions.py,
  shared by `POST /positions/sync` and admin reset-trading-data's resync) queried
  `PositionRepository.list_open(user_id)` — which returns a user's open positions
  across EVERY asset class — then closed any not reported by the ONE asset class's
  broker just queried. A user with e.g. both equity and crypto positions calling
  `POST /positions/sync?asset_class=equity` would incorrectly zero out/close their
  crypto positions locally (broker still holds them — silent local/broker
  divergence, and a later buy signal would then wrongly re-buy since "no open
  position" existed locally). Fixed by skipping any local position whose
  `asset_class` doesn't match the one being synced. Regression test:
  `test_sync_does_not_close_positions_in_other_asset_classes` in tests/test_api.py
  (also required registering a second per-asset-class PaperBroker in
  `_mock_broker_registry()` for "crypto", since `BrokerRegistry.resolve()` requires
  `(broker_name, asset_class)` to be explicitly registered — no wildcard fallback
  once `resolve_broker` forces `paper_mode=False` into the registry lookup).
- FIXED flaky test (2026-08-20): `test_signal_follow_discovers_candidates_without_
  watchlist_or_price_bars` (tests/test_api.py) called `runtime.run_strategies()`
  directly without mocking `src.modules.schedules.market_hours.is_open` —
  `TradingRuntime._evaluate_buy_by_discovery`'s `region_open()` check (gated on
  `schedule.market_hours_enabled`, default True) uses the REAL wall-clock time, so
  the test silently produced ZERO decisions (not just acted=False — the ticker was
  skipped before `_record_decision` ever ran) whenever the Docker build happened to
  run outside 9:30-16:00 America/New_York on a weekday. This is a real, currently-
  reproducible flakiness class: ANY test that calls `run_strategies()`/hits the buy
  or sell evaluation loops without asserting a specific market state must
  `monkeypatch.setattr(market_hours, "is_open", lambda region, now=None: True)`
  (import `from src.modules.schedules import market_hours` — it's a real submodule,
  importable even though not re-exported from `schedules/__init__.py`) or otherwise
  neutralize the gate; don't assume "the tests passed once" means this class of
  test is safe against time-of-day.
- No pre-trade risk/Guardian gate exists at all (not disabled-by-default, fully removed —
  migration 0003_remove_risk.py dropped `daily_losses` table and the `risk` config section
  was deleted from code, no toggle). No circuit breakers, no daily_stats/dashboard chart,
  no manual-order endpoint, no whale/congress/reddit connectors, no multi-region market-hours
  gating. Telegram + Claude connectors are both explicit `DISABLED=True` placeholders.
  Admin user mgmt is create+list only (no edit/reset/delete). `price/regime.py` exists but
  isn't consumed by either built-in strategy. See missing.md (created 2026-07-10 from
  fdiff.md gap analysis) for the full decision list before adding any of these back.
  STALE as of a later audit (2026-09-04): a manual-order endpoint (`POST
  /api/v1/orders/manual`, `ExecutionEngine.place_manual_order`) and multi-region
  market-hours gating (`schedules/market_hours.py`, `_region_open` in runtime.py) were
  both added after this note was written, and `trailing_stop` v2.0.0 now consumes
  `price/regime.py` for its regime-aware ATR multiplier — don't trust this bullet's
  "missing" list at face value, check the current code first.

- 2026-09-04 audit — hunted specifically for LOGIC/business-rule bugs (not
  syntax/type errors) across the whole trading pipeline. Two real findings, plus one
  false-positive worth recording so it isn't re-flagged:
  1. **CONFIRMED BUG — pending broker orders silently treated as filled.**
     `ExecutionEngine.handle_buy`/`handle_sell`/`place_manual_order`
     (src/modules/execution/__init__.py) only branch on
     `result.status == OrderStatus.rejected.value`; every other status — including
     `OrderStatus.pending` — falls through the same path that opens a position,
     records the order as `filled`, and publishes `OrderFilledEvent`.
     `Trading212Broker.place_market_order` (src/modules/com/trading212/__init__.py)
     explicitly returns `status=str(data.get("status", "pending")).lower()`, i.e. a
     real, expected value from that connector. `PaperBroker` always returns
     `"filled"`, which is why this never surfaces in paper/demo testing. There is no
     job anywhere that later reconciles a `pending` order against the broker, so a
     non-instantly-filled market order permanently corrupts local position state
     (wrong `avg_price`, phantom open position) with no way to self-heal. No test
     exercises `OrderStatus.pending`. Fix direction: only the `filled` branch should
     open/update a position and publish `OrderFilledEvent`; `pending` should persist
     the order as pending and be reconciled by a follow-up check.
  2. **CONFIRMED GAP — no validation that `active_buy_strategy`/`active_sell_strategy`
     actually points at a strategy of that direction.** `schema.py` declares both as
     bare `str | None` with no validator; `ConfigService.set_value`
     (src/modules/configs/__init__.py) only checks write permission, never the
     strategy registry; `StrategyRegistryService.get_active`/`get_loaded`
     (src/modules/strategy/registry.py) looks a name up across ALL discovered
     strategies regardless of direction. A trader could (accidentally, or via a
     raw API call bypassing the UI's presumably direction-filtered dropdown) set
     `strategy.active_buy_strategy = "trailing_stop"` (a sell-only strategy) and the
     backend accepts it silently. At runtime this currently fails "safe" — the
     misdirected strategy's own guard (e.g. trailing_stop's `if position is None:
     return acted=False`) means it just never fires — but the user has no way to
     discover their "active" buy strategy is actually inert; nothing surfaces an
     error anywhere. Worth a server-side check in `set_value`/`save_values` that
     resolves the strategy and compares `.direction`.
  3. **FALSE POSITIVE (investigated, NOT a bug — recorded to avoid re-flagging):**
     `AppContext.resolve_broker` (src/api/context.py) hardcodes
     `paper_mode=False` when calling `BrokerRegistry.resolve(...)`, which looks at
     first glance like it defeats `broker.paper_mode` ever routing to the in-memory
     `PaperBroker` (src/modules/broker/paper.py), and that `broker_credentials_required`
     defaulting to `True` in production means Trading212 credentials are always
     required even when `paper_mode=True`. Both are **intentional**, not bugs:
     `tests/test_api.py::test_sync_reflects_broker_positions_after_manual_order`
     documents that an earlier version *did* route `paper_mode=True` to the ephemeral
     in-memory `PaperBroker`, and that broke `POST /positions/sync` (the broker had no
     memory of orders placed against a different, throwaway `PaperBroker` instance
     each call, so sync closed positions that were actually still open). The real
     design (confirmed by a comment in src/api/v1/credentials.py): `broker.paper_mode`
     only switches Trading212's DEMO vs LIVE base URL — "paper trading" means trading
     against Trading212's own demo account (needs its own real Trading212 API
     credentials tied to that demo account), not a fully-local zero-credential
     simulator. Do not "fix" this again without re-reading that test first.

- 2026-09-07 — fixed all 11 Critical/High findings from `docs/bugs.md` (1,2,3,4,5,
  6,7,8,9,10,18); findings 11-17,19-22 deliberately left unfixed (out of scope for
  this pass, still open in bugs.md). Notable implementation decisions/gotchas:
  - **Position identity (1+5):** `uq_position_user_ticker` replaced with a partial
    unique `Index` scoped to `status='open'` on `(user_id, ticker, asset_class)` —
    closed rows can repeat freely (round-trip history preserved), and the same
    ticker can be open in two asset classes at once. `get_open_by_ticker` now takes
    `asset_class`; the execution engine's per-ticker `asyncio.Lock` key gained
    `asset_class` too. Migration 0012. Note: signal-level dedup
    (`SignalRepository.recent_for_ticker`) is still keyed by `(user, ticker,
    direction)` only, NOT asset_class — a latent gap, not fixed here, tests had to
    pass `dedup_window_seconds=0` to exercise the position-identity behavior in
    isolation.
  - **Pending orders (2):** only a broker-confirmed `filled` status now
    opens/mutates a position or publishes `OrderFilledEvent`; anything else is
    persisted as `pending` (new `Order.asset_class` column, migration 0013) and
    reconciled by a new scheduled job (`reconcile_orders`, every
    `schedule.reconcile_orders_seconds`, default 60s) that polls
    `Broker.get_order_status` (new abstract method, implemented on both
    `PaperBroker` and `Trading212Broker`) and finalizes fill/reject there instead.
  - **Reset trading data (6):** `ResetTradingDataIn.asset_class` is now
    `str | None` (`None` = every asset class) — the wipe was never scoped to one
    asset class, so the resync wasn't either. **Response shape changed**:
    `synced` is now `{username: {asset_class: {...}}}` (was flat
    `{username: {...}}`) — updated `src/ui/src/types/index.ts` and
    `pages/Users.tsx` accordingly.
  - **Profit tier race (7):** `handle_sell` re-checks
    `position.profit_tier{N}_taken` (freshly reloaded under the per-ticker lock)
    before selling — relies on the same lock already serializing overlapping
    `run_strategies()` passes (scheduler vs. activation-triggered background task)
    for this to actually close the race.
  - **Stale prices (3):** new `storage.latest_price()` picks the freshest close
    across `1m`/`1h`/`1d` files by timestamp. `StrategyContext.current_price` (new
    field) carries this into strategy evaluation; `trailing_stop.py` uses it for
    stop/tier comparisons (ATR/SMA still computed from the daily dataframe).
    `_watchlist_by_poll_interval("1h")` now also includes any open position not on
    the watchlist at all (defaulted to `market_hours.US`).
  - **Trailing stop doesn't trail (4):** new `Position.high_water_mark` column
    (migration 0014, backfilled to `avg_price` for existing open rows) +
    `PositionRepository.bump_high_water_mark` (monotonic, no-op write if not a new
    peak). `TradingRuntime._evaluate_sell` refetches the position **by id** before
    bumping it — reusing the ORM object from the outer `run_strategies()` loop
    (loaded on an already-closed session) to write would hit the cross-session
    gotcha documented above. `trailing_stop.py`'s stop now trails from
    `high_water_mark`, not `avg_price`; profit tiers are unchanged (still measured
    from entry). Bumped `STRATEGY_VERSION` 2.0.0 -> 2.1.0.
  - **Concurrent bootstrap (8):** new single-row sentinel table
    (`BootstrapLock`, fixed `id=1`, migration 0015) — `bootstrap_first_admin`
    inserts+flushes it before creating the user and catches `IntegrityError`; the
    plain `has_any_user()` count check alone is not atomic under concurrency.
  - **Concurrent failed logins (9):** `UserRepository.increment_failed_attempts`
    does an atomic DB-side `SET failed_login_attempts = failed_login_attempts + 1
    RETURNING ...` instead of a python-level read-then-write, which could lose
    updates and let far more than `MAX_FAILED_ATTEMPTS` guesses through.
  - **Last admin self-demotion (10):** `update_user`'s last-active-admin guard now
    covers a role change away from admin, not just deactivation.
  - **Watchlist asset-class identity (18):** deliberately did **not** do the same
    invasive (schema+migration) treatment as position identity here, since
    `PriceWatchlist.ticker` stays globally unique and the Settings > Watchlist chip
    UI is genuinely ticker-keyed (making a same-ticker-two-asset-classes UI a real
    frontend feature, not just a backend fix). Instead: `upsert()` now rejects a
    conflicting asset_class (`WatchlistAssetClassConflictError` -> 409) instead of
    silently overwriting the existing row's asset_class — this is the second
    alternative bugs.md's own finding 18 write-up explicitly offered ("if ticker is
    intentionally global, reject a conflicting add"). Had to update a pre-existing
    test (`test_price_watchlist_repository_crud`) that asserted the old buggy
    overwrite-on-conflict behavior.
  - General gotcha reconfirmed: `replace_string_in_file` with an `oldString` that
    ends mid-function can leave the ORIGINAL function's tail statements orphaned
    right after a newly-inserted test — always re-read the resulting file after
    inserting a new test between two existing ones, don't trust a "successful"
    edit result alone.

- 2026-09-07 (same day, follow-up pass) — fixed the remaining 11 findings from
  `docs/bugs.md` (11,12,13,14,15,16,17,19,20,21,22), completing all 22. 196 tests
  passing. Notable decisions/gotchas:
  - **must_change_password enforcement (11):** added the check inside
    `require_permission`'s dependency (deps.py), not plain `get_current_user` —
    the change-password route itself uses plain `get_current_user` and must stay
    reachable while the flag is true. This blocks every permissioned action
    (trade, edit credentials, activate a strategy, admin actions) but leaves
    read-only GETs open so a user can still navigate to Settings > Security.
    **Gotcha found along the way:** `POST /api/v1/settings` (save_values) does
    its own permission check (`can_write_key`) via plain `get_current_user`, NOT
    `require_permission` — so it needed its own standalone
    `must_change_password` gate added directly in the route; the
    `require_permission`-based fix alone did not cover it. Any other route using
    plain `get_current_user` with custom in-route permission logic (grep for
    `Depends(get_current_user)` outside `require_permission`) should be checked
    the same way if this rule is ever revisited.
  - **Settings validation (12):** new `validate_settings_values()` in
    `configs/__init__.py`, checked against the same compiled schema
    `GET /settings/schema` already produces (so there's one source of truth, not
    two). Added a `nullable` flag to field metadata, separate from `required` —
    `required=False` was being used for both "has a default value" (e.g.
    `fixed_usd: float = 100.0`) and "genuinely `X | None = None`" (e.g.
    `active_buy_strategy`), so a plain `float` field could previously accept
    `None` as long as it merely had *a* default. Whole request is validated
    before any key is written (all-or-nothing).
  - **Strategy direction validation (13):** both entry points
    (`PATCH /strategies/{name}/activate` and the generic
    `strategy.active_{buy,sell}_strategy` settings keys) now resolve the named
    strategy and reject a direction mismatch or nonexistent name with 400.
  - **Signal vote dedup (14):** the real fix is in
    `SignalSourceRegistry._discover_one` (signal/sources.py) — dedupes by ticker
    *within one source's* raw items (only `discover()`, the bulk endpoint, can
    ever return >1 row per source per ticker; `fetch()` cannot). Also made
    `signal_follow.py` defensively count distinct `.source` names rather than
    raw row count, as a second line of defense.
  - **Order → signal linkage (15):** added `signal_id=signal.id` to all 6
    `orders.create()` call sites in `execution/__init__.py` (buy/sell ×
    filled/pending, plus manual). **Bonus bug found and fixed while doing
    this:** `handle_sell`'s FILLED-branch `orders.create()` call was missing
    `asset_class` entirely (a leftover gap from the earlier pending-order fix —
    the *pending* branch had it, the filled branch didn't). Deliberately did
    **not** attempt to populate `signal_outcomes` (PnL attribution) — bugs.md's
    own fix direction says that "requires defining outcome attribution... before
    populating", i.e. it's an underspecified new feature, not a well-defined bug
    fix; left as a follow-up.
  - **Settings/watchlist partial-apply (19):** frontend-only fix (no JS/TS test
    runner exists in this repo — `npm run build` compiling is the only
    automated check available; verified by careful code review instead).
    `useWatchlistDraft.commit()` switched from `Promise.all` (fails fast, but
    earlier-fired parallel requests may still land) to `Promise.allSettled`,
    tracks failures per-ticker, and merges the post-commit reload so a
    **failed** add/update's attempted draft value is preserved instead of being
    silently wiped by the unconditional reload — a real "add ticker, save
    fails, ticker just vanishes with no error" bug. `Settings.tsx`'s `save()`
    now treats the schema-fields save and the watchlist commit as two
    independent try/catch sections, so a watchlist failure no longer prevents
    the schema fields (already successfully saved moments earlier) from having
    their own dirty state cleared.
  - **Signal-source configured status (20):** new
    `SignalSourceRegistry.is_configured(name)` reuses the exact same
    `_build_connector` resolution `fetch()`/`discover()` already use — so status
    reporting can never disagree with what actually happens at runtime. The old
    code always checked a hardcoded `<name>_base_url` credential for *any*
    credentialed source, which is wrong for finnhub/fmp_rating/fmp_grades
    (API-key-only, `needs_base_url=False`).
  - **Duplicate strategy names (21):** `discover_strategies()`
    (strategy/loader.py) now validates name uniqueness across the *complete*
    result (both `buy/` and `sell/` combined) before returning, raising
    `DuplicateStrategyNameError` with both conflicting file paths. This makes
    every caller (`scan()`, `get_loaded()`, `all_extra_sections()`, and thus
    app startup itself) fail loudly instead of a dict comprehension silently
    keeping "whichever one came last". Deliberately left app startup
    (`src/api/main.py`'s lifespan `scan()`) and `TradingRuntime` unwrapped — a
    collision there is meant to fail loudly per the fix direction's "do not
    publish a partially reconciled registry", not fall back to a "last known
    good" registry (that wasn't asked for).
  - **Backtrader partial sells (22):** `BacktraderLiveBridge`'s `_OrderRecorder`
    now also records the strategy's position size immediately after each
    completed order; the sell translation recovers the pre-sell size
    (`post_size + sell_size`) and computes a real `quantity_pct` from it
    (`None` only for a genuine full exit) instead of always requesting a full
    exit. Buy-side quantity was deliberately left untranslated and documented
    as such: no `BuySignalEvent` in Lucid carries a quantity at all — every
    buy strategy's suggested size (if any) is discarded and recomputed by
    `ExecutionEngine.handle_buy` from `execution.quantity_mode` — this isn't a
    backtrader-specific gap, so fixing it would mean redesigning the
    `BuySignalEvent`/execution-engine sizing contract for every strategy, well
    beyond this one bridge.
  - **Market close boundary (16):** `market_hours.is_open()`'s close comparison
    changed from `<=` to `<` (exclusive close) — a one-line fix.
  - **PaperBroker negative cash (17):** `place_market_order`'s buy branch now
    rejects with `"insufficient cash"` if `quantity * price > self._cash`,
    before mutating any state — matches how a real funded broker would behave;
    `broker.paper_mode` in production routes to Trading212's demo account, not
    this in-memory broker (see the `resolve_broker` false-positive note above),
    so this only affects tests/an explicit custom in-memory broker config.
- FIXED (2026-09-10): `signal_follow`-style discovery candidates (`USES_WATCHLIST
  = False`) never entered the price-fetch pipeline's ticker universe — `_watchlist()`
  only unioned the watchlist and open positions, so a purely-discovered ticker (by
  design never on the watchlist) never got a stored daily bar. `ExecutionEngine.
  handle_buy`'s `_quote()` reads only stored bars, so every resulting buy signal was
  rejected forever with "no price" — the strategy could discover and vote "buy" on a
  ticker but could never actually execute a trade for it. This directly contradicted
  the earlier 2026-08-xx note above ("which happens automatically since watchlist
  tickers are already in the price-fetch pipeline's ticker set") — that assumption
  only holds for `uses_watchlist=True` strategies. Fix: `_watchlist()` now also
  queries every active trader's active buy strategy; if it's `uses_watchlist=False`,
  its currently-discovered candidate tickers (`_discover_buy_candidates`) are unioned
  in too, so the regular daily/intraday pipeline fetches a real price for them like
  any other tracked ticker. Deliberately NOT fetched synchronously inside
  `run_strategies`/`_evaluate_buy_by_discovery` (would add a live network call to
  every strategy-evaluation pass, incl. hitting real Yahoo Finance from
  `test_signal_follow_discovers_candidates_without_watchlist_or_price_bars`, which
  doesn't mock `yahoofinance.fetch_ohlcv`) — same next-scheduled-fetch lag as
  watchlist tickers already have, not instant.
- FIXED (2026-09-10): `SignalService.mark_blocked` appends the execution-level block
  reason (e.g. "no price", "position already open") into `Signal.reasoning`, with a
  comment claiming it's "visible in one place (see GET /api/v1/signals,
  pages/StrategyDetail.tsx)" — but neither actually exposed it: `list_signals`
  (src/api/v1/signals.py) omitted `reasoning` from its response dict entirely, and
  the Signals table (pages/StrategyDetail.tsx `StrategySignals`) had no column for
  it. Net effect: a user could see a signal sitting at status `blocked` (or a
  decision `acted` followed by no order) with literally no way to see why from the
  UI. Fixed both: `reasoning` added to the API response, `Signal` TS type, and a new
  "Reason" column in the Signals table.
- CHANGED (2026-09-10): `TradingRuntime._quote()` (src/api/runtime.py) is now async
  and fetches on-demand instead of only ever reading stored bars. Previously a
  ticker with zero stored bars stayed permanently blocked with "no price" until the
  next scheduled daily/intraday pipeline run (up to ~24h later, and scheduled jobs
  never run at all in sqlite/test mode — see `register_jobs()`). Now: if
  `storage.latest_price()` is `None`, it calls `self._pipeline().run_backfill(ticker,
  days=5)` once, then re-reads; any exception during the fetch is caught and logged,
  falling through to the pre-existing "no price"/`0.0` block behavior. This
  complements (doesn't replace) the earlier `_watchlist()` fix above — that fix gets
  discovery-only tickers into the *scheduled* pipeline; this fix additionally
  unblocks the very first evaluation before that scheduled fetch ever runs.
- TEST-ISOLATION GOTCHA (2026-09-10): mutating `ctx.settings.price.storage_path`
  (or any other `ctx.settings.*` field) on the shared `client` fixture's already-
  running `AppContext` — i.e. `runtime.ctx.settings.price.storage_path =
  str(tmp_path)` *after* `create_app()`/lifespan already started — does NOT reliably
  isolate writes to `tmp_path` for code paths reached from background-style calls
  (e.g. `TradingRuntime.run_strategies()` triggering `ExecutionEngine.handle_buy` →
  the on-demand `_quote()` fetch above). A test doing this leaked a real "NFLX"
  parquet file into the default `/data/prices` path, which then showed up as a
  phantom ad-hoc entry (see `list_watchlist`'s "has stored bars but no watchlist
  row" scan in src/api/v1/prices.py) in FOUR unrelated, later-running tests reading
  the default storage path. Fix: build a fully separate `AppContext.build(...)` +
  `create_app(ctx)` + own `TestClient` for any test that needs a custom
  `storage_path`, and set `ctx.settings.price.storage_path` *before* `create_app()`
  — matches the pre-existing pattern in `test_admin_price_coverage_report_reflects_
  stored_bars`. Never mutate `ctx.settings` on the shared `client` fixture's context
  once the app has already started, even though nothing prevents you from doing so
  at the Python level.
- `tmp/trading-212-api.yaml` is the official Trading212 REST API reference
  (OpenAPI spec) — check it before guessing at request/response schemas or error
  semantics for `src/modules/com/trading212/`.
- (2026-09-10) Auto-sized buys were failing with `HTTP 400 for
  /api/v0/equity/orders/market`. `Trading212Client.request()` used to discard the
  response body on 4xx; fixed to include it (truncated) in the raised
  `Trading212Error`, which then revealed the real cause: `{"type":"/api-errors/
  quantity-precision-mismatch", ..., "detail":"invalid quantity precision 3"}`.
  Trading212 rejects most equities unless `quantity` is a whole number — only a
  subset of instruments allow fractional shares, and the API exposes no
  per-instrument way to know which. `compute_buy_quantity()` (src/modules/
  execution/sizing.py) did `usd / price` with no rounding, producing 3+ decimal
  quantities; manual orders never hit this because the user types a clean number.
  Fixed by flooring to a whole share count (`math.floor`) — always valid
  regardless of what precision an instrument supports, at the cost of losing
  sub-share sizing precision for the instruments that do allow it.
  Separately, `HTTP 404 ... {"type":"/api-errors/entity-not-found","detail":
  "Ticker does not exist"}` for tickers like `CRGY` is NOT a bug: `resolve_ticker`
  (src/modules/com/trading212/__init__.py) intentionally returns the raw symbol
  unchanged when it finds no match in Trading212's instrument list, by design, so
  Trading212 rejects it with a clear error rather than the code silently failing.
- (2026-09-10) `reconcile_pending_orders` was hammering `/api/v0/equity/orders/{id}`
  (404 once filled) then `/api/v0/equity/history/orders` per pending order in a
  tight loop, with no cross-order throttling. That history endpoint has its own
  much tighter Trading212 rate limit (seen: 6 req/60s) than the general 50/60s
  limit, so a batch of pending orders exhausted it and got a run of `429`s. The
  retry logic in `Trading212Client.request()` used a fixed exponential backoff
  (`0.2 * 2**attempt`) that ignored the `Retry-After` header Trading212 sends on
  429 (e.g. 4-5s) — so all 3 retry attempts re-hit the same still-exhausted window
  and gave up. Fixed: `_retry_delay()` now reads `Retry-After` and sleeps that long
  instead of the short exponential backoff when present. No cross-order rate
  limiter was added (order left as-is) — this only fixes wasted/futile retries
  within a single request's retry loop, not overall request volume across a
  reconcile pass.
- (2026-09-10) Added proactive rate-limit tracking to `Trading212Client`
  (`_rate_limit_reset`, `_bucket_key`, `_record_rate_limit`, `_wait_for_rate_limit`
  in src/modules/com/trading212/__init__.py): every response's
  `x-ratelimit-remaining`/`x-ratelimit-reset` headers are recorded per
  endpoint-template bucket (numeric path segments collapsed to `{id}`, since
  Trading212 limits e.g. `/equity/orders/{id}` as one bucket regardless of the
  actual id — confirmed against `tmp/trading-212-api.yaml`: `orderById` is
  `1 req/1s`, `/equity/history/orders` is `6 req/60s`, vastly tighter than the
  general `50 req/1m0s`). Before firing a request, the client now waits out any
  bucket it already knows is exhausted instead of firing and getting a 429.
  Confirmed relevant per-endpoint values only exist in the API spec's per-path
  descriptions, not the general "Rate Limiting" doc section — `Retry-After` itself
  isn't documented there either, only seen live in response headers. This is
  per-`Trading212Client` instance state, which is safe because `AppContext`
  already caches one client per (user_id, asset_class, broker_name, base_url,
  key_id, secret_key) (see context.py `_broker_cache` comment) — a fresh client
  per call would make this tracking useless.
