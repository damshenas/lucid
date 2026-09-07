# Application Logic Audit

Audit date: 2026-09-04

**Update (2026-09-07):** all 22 findings in this document have been fixed — see
`docs/agent-notes.md`'s 2026-09-07 entries for implementation details and any
scope deviations (notably findings 15 and 22, which were fixed partially by
deliberate, documented scope decisions; and finding 18, fixed via the
document's own second alternative rather than full asset_class identity).

## Scope

This audit covers application behavior and trading/business rules. It excludes
syntax, linting, infrastructure, Docker, deployment, and deliberately deferred
features such as the pre-trade risk gate and daily P&L dashboard.

Findings were traced through their API, service, repository, broker, strategy,
and persistence paths. Previously fixed items in `docs/agent-notes.md` are not
reopened unless the current implementation still has a distinct failure mode.

A second independent sweep covered the complete frontend workflow, every database
model/repository, the remaining API routes, external signal-source contracts, price
storage, and disabled-but-present application modules. Static review cannot prove
that no undiscovered bug exists; this document records every issue substantiated by
the reviewed code paths as of the audit date.

Severity means:

- **Critical:** local trading state can become materially false or a normal trade
  lifecycle is permanently broken.
- **High:** money-affecting behavior, cross-asset corruption, or an authorization
  rule can fail under a realistic trigger.
- **Medium:** a valid workflow silently becomes inert or records materially
  incomplete business data.
- **Low:** a real but narrow boundary issue or a non-production behavior defect.

## Confirmed Bugs

### 1. A closed ticker can never be opened again

**Severity:** Critical

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/modules/db/models/position.py:15` uniquely constrains positions by
  `(user_id, ticker)` across both open and closed rows.
- `src/modules/db/repositories/position.py:15-23` only returns an open row.
- `src/modules/execution/__init__.py:151-160` and `:351-361` create a new position
  when no open row exists.
- `src/api/v1/positions.py:49-60` does the same during broker reconciliation.

**Trigger:** Buy a ticker, fully sell it so its row becomes `closed`, then buy the
same ticker again or sync it back from the broker.

**Result:** The open-position lookup returns no row, but insertion violates
`uq_position_user_ticker`. Automated execution blocks the signal after an internal
database error; manual ordering returns an error; broker sync can fail. A trader
cannot complete a second round trip in the same ticker.

**Fix direction:** Either permit multiple historical position rows with uniqueness
limited to an open position, or deliberately reopen/reset the existing closed row.
The latter loses clean round-trip history unless history is stored elsewhere.

**Missing test:** buy -> full sell -> buy the same ticker again.

### 2. Pending or unknown broker orders are recorded as filled

**Severity:** Critical

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/modules/broker/base.py:24-31` explicitly allows `filled`, `pending`, and
  `rejected` results.
- `src/modules/com/trading212/__init__.py:144-152` defaults a response without a
  status to `pending`.
- `src/modules/execution/__init__.py:144`, `:231`, and `:339` branch only on
  `rejected`. Every other value follows the fill path.

**Trigger:** Trading212 accepts a market order but reports it as `pending`, or
returns another non-rejected state.

**Result:** Lucid immediately creates/reduces a position, writes an order with
`status="filled"`, marks the signal acted, and publishes `OrderFilledEvent`. If the
broker later rejects, partially fills, or fills at another price, local state is
false. The current position sync does not reconcile pending order state.

**Fix direction:** Only `filled` may mutate positions. Persist `pending` orders and
reconcile them by broker order ID, including rejected, cancelled, and partial-fill
outcomes. Unknown statuses should fail closed rather than mean filled.

**Missing tests:** pending buy, pending sell, pending manual order, and unknown
status.

### 3. Strategy polling uses stale daily prices and ignores fetched intraday bars

**Severity:** High

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/api/runtime.py:65-69` resolves execution quotes only from the `1d` file.
- `src/api/runtime.py:238`, `:269`, and `:340` pass only `1d` data to sell,
  watchlist-buy, and discovered-buy strategies.
- `src/api/runtime.py:108-148` fetches `1m`/`1h` bars into separate files, but no
  strategy or execution quote reads those files.
- `src/conf/default.yml` runs strategy evaluation every 300 seconds while daily
  prices are fetched once at hour 22.

**Trigger:** An open position crosses its stop or profit target intraday before the
next daily fetch, or a discovered buy candidate has moved materially since the last
daily close.

**Result:** The five-minute strategy job repeatedly evaluates the same daily close.
The sell strategy can miss an intraday stop or profit tier for the entire session.
Buy sizing also uses the stale daily price even though the broker receives a market
order at the current price.

This is especially severe for positions removed from the watchlist:
`_watchlist_by_poll_interval()` includes watchlist rows only, so such positions do
not receive intraday updates at all.

**Fix direction:** Define a latest-quote source independent of indicator history.
Use current intraday data for stop/tier evaluation and sizing while retaining daily
history for SMA/ATR calculations. Open positions must remain in the intraday fetch
universe even when not on the buy watchlist.

**Missing tests:** a stop crossed only in the latest intraday bar and a held,
non-watchlist ticker receiving intraday updates.

### 4. The advertised trailing stop does not trail

**Severity:** High business-logic mismatch

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:** `strategies/sell/trailing_stop.py:83-87` calculates:

```python
stop_price = entry - snap.atr * effective_atr_mult
```

No high-water mark, highest close/high since entry, or persisted trailing stop is
tracked anywhere in the position model.

**Trigger:** A position entered at 100 rises to 140 and then retreats. With ATR 5
and multiplier 3, the stop remains 85 instead of trailing behind the 140 peak.

**Result:** The strategy can give back the entire unrealized gain and still hold
until the price falls below the original entry-based loss threshold. This is a
static ATR stop-loss, not the trailing stop promised by the strategy name and
description.

**Fix direction:** Persist a high-water mark or monotonic trailing-stop value per
position and calculate the stop from that state. Alternatively, rename and document
the strategy as an entry-anchored ATR stop if the current rule is intentional.

**Missing test:** price rises substantially, then retraces through a stop based on
the post-entry peak while remaining above the entry-based stop.

### 5. Position identity omits asset class

**Severity:** High

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/modules/db/models/position.py:15` uses `(user_id, ticker)` rather than
  `(user_id, ticker, asset_class)`.
- `src/modules/db/repositories/position.py:15-23` does not filter by asset class.
- `src/modules/execution/__init__.py:78-82` also locks by `(user_id, ticker)` only.
- `src/api/v1/positions.py:49-63` can update a same-symbol row using holdings from
  whichever asset-class broker is currently being synchronized.

**Trigger:** A user trades the same symbol in two asset classes, or two instruments
normalize to the same plain ticker. A concrete ambiguous symbol is `BTCUSD`, which
can represent a crypto pair or an FX/CFD instrument depending on the broker.

**Result:** One asset-class buy can be blocked as "position already open", merged
into the other class's position, sold through the wrong broker, or overwritten by a
sync from another asset class. The schema cannot represent both holdings.

Trading212 normalization compounds the issue:
`src/modules/com/trading212/__init__.py:117-129` strips the exchange suffix, so two
exchange instruments with the same base symbol also collapse to one local identity.

**Fix direction:** Carry a stable instrument identifier and asset class through
positions, orders, signals, locks, quote storage, and reconciliation. At minimum,
all position uniqueness/lookups/locks must include `asset_class`.

**Missing tests:** same user and same ticker in two asset classes; two broker
instrument tickers that normalize to the same base symbol.

### 6. Resetting trading data drops live positions in other asset classes

**Severity:** High

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/api/v1/admin.py:282-286` deletes every order, signal, decision, and position
  for each target user without asset-class filtering.
- `src/api/v1/admin.py:302-305` then synchronizes only `body.asset_class`, whose
  default is `equity` (`:48-51`).

**Trigger:** A trader has live equity and crypto positions. An administrator calls
`POST /api/v1/admin/reset-trading-data` with the default request body.

**Result:** All local positions are deleted, but only equity holdings are restored.
The broker still holds crypto while Lucid shows no crypto position. A later buy can
duplicate the real holding, and its sell strategy no longer manages that position.

**Fix direction:** Because the endpoint intentionally wipes all trade history,
resynchronize every configured asset-class broker after the wipe. If the endpoint
is intended to reset only one asset class, every repository deletion must instead
be scoped consistently, which requires adding asset class to orders or deriving it
reliably through positions/signals.

**Missing test:** reset a trader holding equity and crypto, then verify both live
holdings are restored.

### 7. A profit tier can execute twice when strategy runs overlap

**Severity:** High

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- Scheduled jobs have `max_instances=1` in
  `src/modules/schedules/__init__.py:78-86`.
- Strategy activation bypasses that scheduler guard by directly adding
  `runtime.run_strategies` as a FastAPI background task in
  `src/api/v1/settings.py:90-96` and `src/api/v1/strategies.py:70-77`.
- `src/api/runtime.py:371-374` publishes every acted sell decision even when
  `_record_decision()` deduplicates the log row.
- `src/modules/execution/__init__.py:192-260` serializes sells by ticker, but never
  checks whether `event.profit_tier` was already taken before selling.

**Trigger:** A scheduled strategy pass and an activation-triggered pass both read
`profit_tier1_taken=False` before either sell commits.

**Result:** Both publish the same tier event. Execution serializes them, but the
second execution merely reloads the reduced open position and sells the configured
percentage again despite seeing the tier marker. With 100 shares and a 33% tier,
the first event sells 33 and the second sells 22.11, producing a 55.11-share exit
instead of 33.

**Fix direction:** Make tier consumption atomic in execution: after acquiring the
lock and reloading the position, reject an event whose tier is already marked.
Also use one shared single-flight guard for every `run_strategies()` entry point;
decision-log deduplication is not an execution idempotency mechanism.

**Missing test:** two concurrent identical tier events against one position.

### 8. Concurrent first-run setup can create multiple administrators

**Severity:** High

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/modules/authentication/service.py:55-63` performs `count_users()` and
  `create()` as separate operations without a lock or singleton constraint.
- `src/api/v1/auth.py:61-68` commits only after that check/create sequence.
- `src/modules/db/models/user.py:17` makes usernames unique, but does not constrain
  the system to one successful bootstrap transition.

**Trigger:** Two initial `/api/v1/auth/setup` requests with different usernames run
before either transaction commits.

**Result:** Both can observe zero users and both become administrators. The
first-run security boundary is not atomic.

**Fix direction:** Serialize bootstrap with a database advisory/row lock or an
atomic bootstrap sentinel. Treat the losing concurrent request as `409 Conflict`.

**Missing test:** concurrent setup requests with different usernames.

### 9. Concurrent failed logins defeat the configured attempt limit

**Severity:** High

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:** `src/modules/authentication/service.py:97-110` reads
`failed_login_attempts`, increments it in Python, and writes the absolute value back
without row locking or an atomic update.

**Trigger:** Send many wrong-password requests for one username concurrently while
they all observe the same counter value.

**Result:** The requests overwrite one another with the same `N + 1` value. A large
batch of guesses can count as one failed attempt, allowing far more than five
password guesses before the 15-minute lockout. The existing test in
`tests/test_auth.py:88-98` covers sequential requests only.

**Fix direction:** Atomically increment and return the counter in the database, or
lock the user row for the whole check/update operation. Lock creation and expiry
must be part of the same atomic transition.

**Missing test:** concurrent failed logins followed by a correct password.

### 10. The last active administrator can demote their own account

**Severity:** High

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:** `src/api/v1/admin.py:87-113` protects deactivation of the last active
admin, but applies a role change without the equivalent check.

**Trigger:** The only active administrator sends:

```json
{"role": "trader"}
```

to `PATCH /api/v1/admin/users/{their_id}`.

**Result:** The request succeeds and the installation has no active administrator
with `manage_users` or system-settings permissions. The existing access token does
not help because authorization reloads the current database role on each request.

**Fix direction:** Reject any role change that would leave zero active admins. Use
one invariant check for role changes, deactivation, and deletion.

**Missing test:** the sole admin attempts to change their own role.

### 11. `must_change_password` is informational, not enforced

**Severity:** Medium

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- New users and password resets set `must_change_password=True` in
  `src/modules/authentication/service.py:65-77` and
  `src/api/v1/admin.py:126-138`.
- Login returns the flag in `src/api/v1/auth.py:48-55` but still issues normal
  access and refresh tokens.
- `src/api/deps.py:27-48` checks only token validity and `is_active`; permission
  checks do not inspect `must_change_password`.

**Trigger:** A trader logs in with an administrator-assigned temporary password and
ignores the frontend's change-password flow, using the API directly.

**Result:** The trader can place manual orders, edit credentials, activate
strategies, and refresh the session indefinitely without changing the temporary
password. The backend does not enforce the business meaning of "must change".

**Fix direction:** While the flag is true, permit only authentication status,
refresh/logout as needed, and change-password endpoints. Enforce this in a shared
dependency rather than in the UI.

**Missing test:** a newly created trader cannot call `/api/v1/orders/manual` before
changing the password.

### 12. Settings accept unknown, null, and wrong-typed values without validation

**Severity:** Medium

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/api/v1/settings.py:27-29` accepts `dict[str, Any]`.
- `src/modules/configs/__init__.py:226-241` checks only secret naming and write
  permission before persisting.
- `src/modules/configs/__init__.py:187-222` lets a higher-precedence row containing
  `None` overwrite a valid default.
- `src/ui/src/pages/Settings.tsx:83-89` converts a cleared numeric field with
  `parseInt()`/`parseFloat()`. The resulting `NaN` is serialized to JSON as `null`,
  so this is reachable through the normal UI rather than only a handcrafted request.
- The `LucidConfig` model validates only `default.yml` at startup, not database
  overrides.

**Trigger:** An admin posts `{"execution.fixed_usd": null}`, an invalid enum, or a
string where a numeric value is required. A trader can do the same for personal
`strategy.*` parameters.

**Result:** Invalid values persist and mask valid defaults. For example,
`float(None)` in `compute_buy_quantity()` prevents buys; invalid strategy numbers
make evaluations fail; an invalid log level is committed before live level
application raises. The API may report failure after the corrupt value is already
saved.

**Fix direction:** Build a validation map from `LucidConfig` plus each strategy's
`CONFIG_SCHEMA`; reject unknown keys, `None` for non-optional fields, wrong types,
invalid enums, and nonsensical ranges before writing any row. Validate the complete
request first, then persist atomically so a multi-key save cannot partially apply.

**Missing tests:** null numeric override, invalid enum, unknown key, malformed
strategy parameter, and one invalid key in a multi-key request.

### 13. Active strategies can be assigned to the wrong direction

**Severity:** Medium

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/api/v1/strategies.py:63-69` checks that a strategy exists but does not compare
  `LoadedStrategy.direction` with the requested direction.
- The generic settings endpoint also accepts arbitrary names for
  `strategy.active_buy_strategy` and `strategy.active_sell_strategy`.
- `src/modules/strategy/registry.py:71-78` resolves an active strategy by name only.

**Trigger:** Call
`PATCH /api/v1/strategies/trailing_stop/activate?direction=buy`, or save the same
mapping through `/api/v1/settings`.

**Result:** The backend accepts an inert or semantically inverted configuration.
The built-in trailing stop returns "no open position" in the buy path, so buying
silently stops. A custom strategy may emit an event of the wrong type and execute
behavior the selected direction did not intend.

**Fix direction:** Resolve the strategy during validation and require its declared
direction to match the target slot. Reject missing or mismatched strategies with a
clear `400` response.

**Missing tests:** activating a sell strategy as buy and vice versa through both
activation entry points.

### 14. Signal-provider voting counts rows, not distinct providers

**Severity:** Medium

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `strategies/buy/signal_follow.py:61-72` counts every answered `ExternalSignal`
  row in `buy_votes`.
- `src/api/runtime.py:316-320` groups discovery results by ticker without
  deduplicating source names.
- `src/modules/com/tradingview/__init__.py:76-98` strips exchange prefixes but does
  not deduplicate the resulting base ticker.

**Trigger:** One provider returns two rows that normalize to the same ticker, such
as same-symbol instruments on two exchanges. Both rows have `source="tradingview"`
and a buy direction.

**Result:** `min_buy_votes=2` is satisfied by two rows from one provider, despite
the documented rule requiring two different signal providers to agree. Confidence
is also inflated.

**Fix direction:** Reduce to at most one normalized opinion per `(source, ticker)`
before strategy evaluation, then count unique source names. Define how conflicting
duplicate opinions from one source are resolved.

**Missing test:** duplicate buy rows from one source plus no vote from the other
source.

### 15. Orders are never linked to their originating signals

**Severity:** Medium business-data gap

**Status:** FIXED (2026-09-07, signal_id linkage only — signal_outcomes
population/PnL attribution was explicitly left as a follow-up; see
docs/agent-notes.md).

**Evidence:**

- `src/modules/db/models/order.py:23-26` defines `Order.signal_id`.
- All three order creation paths in `src/modules/execution/__init__.py:161`, `:253`,
  and `:380` omit `signal_id`, even though each path has already loaded the signal.

**Trigger:** Any automated or manual order fills.

**Result:** The order row cannot identify which exact signal caused it. This breaks
end-to-end auditability when several strategy evaluations exist for the same
ticker, and prevents reliable attribution of later P&L to a signal.

Related gap: `SignalService.record_outcome()` in
`src/modules/signal/__init__.py:103-117` has no production caller, so
`signal_outcomes` remains empty. This is not currently exposed in the UI, but it
means the persisted outcome model is nonfunctional.

**Fix direction:** Set `signal_id` on every order. Define outcome attribution for
partial sells and multiple fills before populating `signal_outcomes`.

**Missing tests:** filled order references its signal; closing a position records
the intended outcome exactly once.

### 16. Market close is treated as open at the exact close timestamp

**Severity:** Low

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:** `src/modules/schedules/market_hours.py:45` uses:

```python
hours.open_time <= local.time() <= hours.close_time
```

**Trigger:** Evaluation at exactly 16:00:00 US, 16:30:00 EU, or 15:00:00 EM local
time.

**Result:** The market reports open at the first instant at which it should be
closed. A boundary-timed strategy/fetch can run once after the configured session.

**Fix direction:** Make the close boundary exclusive.

**Missing test:** exact open and exact close timestamps for each region.

### 17. The in-memory PaperBroker allows negative cash

**Severity:** Low, non-production path

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:** `src/modules/broker/paper.py:53-62` subtracts buy cost without checking
available cash and always returns a fill.

**Trigger:** Submit a paper buy whose cost exceeds `_cash`.

**Result:** Cash becomes negative and an order that a funded broker would reject is
reported as filled, reducing the value of execution tests that use this broker.

**Reachability caveat:** The normal application path deliberately uses Trading212's
demo account for `broker.paper_mode`; `AppContext.resolve_broker()` does not route
that flag to this in-memory broker. The defect primarily affects tests or an
explicit custom/in-memory broker configuration, not normal production trading.

**Fix direction:** Reject buys whose cost exceeds available cash, unless margin is
explicitly modeled.

### 18. Watchlist identity omits asset class and silently reclassifies a ticker

**Severity:** High

**Status:** FIXED (2026-09-07, with a scope deviation from the fix direction below — see docs/agent-notes.md).

**Evidence:**

- `src/modules/db/models/price.py:20` makes `ticker` globally unique without
  `asset_class`.
- `src/modules/db/repositories/price.py:31-61` looks up by ticker alone and changes
  the existing row's `asset_class` during `upsert()`.
- `src/api/v1/prices.py:24-29` accepts asset class as part of a watchlist entry, and
  the frontend presents asset-class-specific watchlist views.

**Trigger:** Add `BTCUSD` to one asset class, then add the same normalized ticker to
another asset class.

**Result:** The second add succeeds by silently changing the first row's asset
class. The original watchlist entry disappears from its asset-class view, its broker
and strategy context changes, and both instruments cannot be tracked concurrently.
This is the watchlist equivalent of finding 5 and also feeds the ticker-only price
storage collision.

**Fix direction:** Identify watchlist and stored price series by a stable instrument
identifier plus asset class/exchange. If ticker is intentionally global, reject a
conflicting add instead of silently reclassifying the existing row.

**Missing test:** add the same ticker to two asset classes and verify neither entry
is overwritten.

### 19. The combined Settings save can partially apply and discard failed edits

**Severity:** Medium

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/ui/src/pages/Settings.tsx:91-105` commits schema settings first and then
  commits the watchlist through separate API requests.
- `src/ui/src/hooks/useWatchlistDraft.ts:113-137` sends all watchlist mutations in
  parallel, where each request commits independently.
- Its `finally` block reloads server state into both `saved` and `draft`, including
  after only some requests succeeded.

**Trigger:** Save schema changes together with multiple watchlist changes, and have
one watchlist request fail after the settings request or another watchlist request
has succeeded.

**Result:** The page reports a generic save failure even though some changes are
already permanent. Schema fields remain marked dirty despite being saved, while a
failed watchlist edit can disappear from the draft during the unconditional reload.
The user cannot tell what applied and can lose the unsaved operation they need to
retry.

**Fix direction:** Treat each section as an explicit result and preserve failed
draft operations. Prefer a backend batch endpoint if the page promises one atomic
Save action; otherwise report partial success and clear/reload only the operations
confirmed as saved.

**Missing test:** one successful and one failed watchlist mutation combined with a
successful settings save.

### 20. Signal-source status checks the wrong credentials for Finnhub and FMP

**Severity:** Medium

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/api/v1/signals.py:62-80` considers every credentialed source configured only
  when `<source>_base_url` resolves.
- `src/api/v1/credentials.py:47-64` defines only `finnhub_api_key` and
  `fmp_api_key`; neither provider has a configurable base URL.
- `src/modules/signal/sources.py:145-179` correctly models these sources as
  `needs_base_url=False`, and both FMP source names share credential prefix `fmp`.

**Trigger:** Configure a valid Finnhub or FMP API key, then call
`GET /api/v1/signals/sources`.

**Result:** Finnhub is reported unconfigured because `finnhub_base_url` does not
exist. `fmp_rating` and `fmp_grades` are also reported unconfigured because the
endpoint looks for per-source base URLs instead of their shared `fmp_api_key`.
Actual fetches use the correct key, so the status endpoint contradicts runtime
behavior.

**Fix direction:** Expose one source-level configuration check from
`SignalSourceRegistry` that honors `requires_credentials`, `needs_base_url`, and
`credential_prefix`; use it in both status reporting and connector construction.

**Missing test:** each API-key-only source reports configured after its catalog key
is saved, including both FMP aliases sharing one key.

### 21. Duplicate strategy names silently shadow another strategy

**Severity:** Medium

**Status:** FIXED (2026-09-07) — see docs/agent-notes.md.

**Evidence:**

- `src/modules/strategy/loader.py:150-164` returns every discovered file without
  validating that `STRATEGY_NAME` is unique.
- `src/modules/strategy/registry.py:37-42` converts that list to a dictionary keyed
  by name, silently retaining only the last file with a duplicate name.
- `src/modules/db/repositories/strategy.py:25-56` also treats name as the registry
  identity and overwrites its file path and direction.

**Trigger:** Two built-in/git-synced strategy files, potentially one buy and one
sell file, declare the same `STRATEGY_NAME`.

**Result:** One strategy disappears without a scan error. Discovery order decides
which implementation, direction, config schema, and source list becomes active.
Because sell files are discovered after buy files, a same-name sell strategy can
silently replace a buy strategy and compound finding 13.

**Fix direction:** Validate name uniqueness across the complete discovery result and
fail the scan with both conflicting paths. Do not publish a partially reconciled
registry when a collision exists.

**Missing test:** two files in the same direction and two files in opposite
directions declaring the same name.

### 22. Backtrader live bridge converts partial sells into full exits

**Severity:** Medium, currently dormant integration

**Status:** FIXED (2026-09-07, sell side only — buy-side quantity was determined
to be out of scope; see docs/agent-notes.md).

**Evidence:**

- `src/modules/backtrader/__init__.py:92-96` records the completed Backtrader order
  size.
- `src/modules/backtrader/__init__.py:104-119` discards that size when constructing
  both buy and sell events.
- `src/modules/bus/events.py:25-34` defines `SellSignalEvent.quantity_pct=None` as a
  full exit.
- `src/modules/execution/__init__.py:215-218` therefore sells the entire local
  position.

**Trigger:** A Backtrader strategy completes a partial sell, such as selling 2 of a
10-share position, through `BacktraderLiveBridge.run_live()` connected to Lucid's
execution bus.

**Result:** The bridge emits a sell signal without quantity information and Lucid
liquidates all 10 shares. Buy order sizes are also discarded and recalculated by
Lucid's configured sizing rule, so the bridge does not faithfully translate either
side's Backtrader order size.

The bridge is not currently invoked by a production route, but it is a public module
with Docker-tested behavior and is described as a live integration.

**Fix direction:** Define an explicit quantity contract for signal events and map
Backtrader's completed order size against the live position. If the bridge is meant
to emit direction-only signals, rename/document it accordingly and do not present
it as translating orders.

**Missing test:** a Backtrader strategy partially sells a position and the emitted
event preserves that quantity rather than requesting a full exit.

## Source Coverage Accounting

The final inventory covered all code-bearing locations under `src/`:

- **100 Python files:** every nontrivial API, configuration, authentication,
  authorization, broker, execution, bus/cache, database model/repository,
  encryption, price, schedule, signal, strategy, backtesting, connector, and data
  migration/sync path was reviewed. Empty/barrel `__init__.py` files were accounted
  for as having no behavior.
- **51 TypeScript/TSX files:** every route page, hook, API client, auth/permission
  helper, navigation component, settings workflow, and reusable control was
  reviewed. Pure presentation components were checked for state/event behavior and
  otherwise excluded from business-rule findings.
- **Configuration/assets:** `src/conf/default.yml` was reviewed with its Pydantic
  model and runtime consumers. `index.css`, `index.html`, `package.json`, and
  `tsconfig.json` were inventoried but excluded because visual styling, build
  configuration, syntax, and infrastructure are outside this audit.
- **Auxiliary modules:** health, logging, HTTP debug, network binding, launch, and
  database bootstrap code were inspected to determine scope. Infrastructure-only
  behavior was excluded; scripts that mutate application prices or strategies were
  included.

Built-in strategy files live outside `src/` under `strategies/`; they were also
reviewed because they directly control trading behavior, producing findings 4 and
14 and supporting findings 3 and 7.

This is complete static coverage of the repository state on the audit date, not a
mathematical guarantee that no bug remains. Runtime-only provider behavior,
production concurrency schedules, and live broker payload variants still require
targeted tests or observed production traces to prove.

## Reviewed Preliminary Claims Not Classified as Current Bugs

### Signal deduplication ignores strategy/source

`SignalService` intentionally documents its cooldown as one acted signal per
`(user, ticker, direction)`, not per strategy. An acted buy also creates an open
position, and the execution engine independently blocks another buy while that
position remains open. If the position is sold inside the cooldown window, blocking
an immediate rebuy is consistent with a ticker-level cooldown. This should remain a
product decision, not be changed silently to per-source deduplication.

### Discovery candidates default to US market hours

The current discovery-capable sources are Finviz's US screens and TradingView's
hard-coded `america` stock scanner. `_DiscoveredCandidate.asset_class="equity"` and
the US-hours fallback match that current contract. Region metadata becomes required
before a non-US discovery source is added, but current behavior is not wrong.

### Tier 2 can fire before tier 1

The tier checks in `trailing_stop.py` are ordered and return immediately. Because
the configured tier-2 threshold is normally higher, a first evaluation above both
thresholds fires tier 1 first. Configuration validation still needs to reject
inverted thresholds; that belongs under finding 12.

### Order events have no production subscribers

Positions and orders are updated synchronously before `OrderFilledEvent` is
published, so the lack of another subscriber does not drop core state. The events
are currently extension hooks rather than required state transitions.

### Migration 0007 downgrades analysts to `viewer`

This is an Alembic downgrade/operational problem and is outside this audit's
application-logic scope. It should be handled in a migration audit, not mixed into
the trading logic list.

## Recommended Fix Order

1. Fix position lifecycle/identity and pending-order handling (findings 1, 2, 5).
2. Make current prices usable by strategy/execution and implement a real trailing
   state rule (findings 3, 4).
3. Repair cross-asset reset and tier execution idempotency (findings 6, 7).
4. Make bootstrap, lockout, and last-admin transitions atomic (findings 8-10).
5. Enforce password-change, config, and strategy-direction rules server-side
   (findings 11-13).
6. Correct vote identity and signal/order attribution (findings 14, 15).
7. Correct watchlist identity, save semantics, and source status reporting
  (findings 18-20).
8. Reject duplicate strategies and preserve Backtrader order intent
  (findings 21-22).
9. Address the narrow boundary/test-broker defects (findings 16, 17).

Every code fix should add a regression test for the trigger described above. Per
repository policy, validation must run only through:

```bash
docker build -f docker/Dockerfile -t lucid-test .
```