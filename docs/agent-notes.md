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
