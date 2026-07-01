# Lucid — Implementation Milestones

> Step-by-step milestones to build Lucid from scratch.
>
> **Source-of-truth hierarchy** (highest wins):
> 1. `plan.md` — final refined plan **(AUTHORITATIVE — build to this)**
> 2. `new_plan.md` — design exploration & Q&A
> 3. `new.md` — original redesign prompt (intent/context)
> 4. `CLAUDE.md` — legacy Dealer system (reference only, do not copy design)
>
> `plan.md` is the improved, authoritative spec. Its structure and naming govern the
> build; the earlier open decisions are resolved in its favor (see **§ Resolved
> structure decisions**).

---

## 0. Resolved design questions (from `new.md`)

| Question | Decision | Rationale |
|---|---|---|
| Python or TypeScript? | **Python 3.12+** backend, **React + TS** frontend | backtrader/pandas/numpy/yfinance have no production TS equivalents |
| Standalone DB? | **PostgreSQL** (asyncpg + SQLAlchemy 2.0 async) | real concurrency, JSONB, timezone-aware timestamps |
| Treat asset classes differently? | **Yes, behind one shared interface** | `AssetClass` enum (`equity`/`commodity`/`crypto`/`fx`); every market-touching module takes `asset_class` |
| Price/time-series storage | **Parquet files on disk** (`/data/prices/`) | cheap, portable, fast for backtesting; not in Postgres |

---

## Resolved structure decisions (per `plan.md`)

All earlier open decisions are now settled by `plan.md`:

1. **DB layout** — everything lives under `src/modules/db/` (`connection.py`, `models/`,
   `repositories/`); **migrations at repo root `alembic/`** (not `src/db/`).
2. **Order pipeline module** — named **`execution`** (`src/modules/execution/`). It makes
   no trading decisions; strategies decide, it executes.
3. **`git` module** — lives under **`src/modules/com/git/`** (git pull for strategy sync).
4. **Strategies** — flat, one `.py` per strategy in `strategies/buy/` and
   `strategies/sell/` (**no subdirectories**).
5. **Logging** — **plain text**, Python `logging` with a simple formatter
   (`YYYY-MM-DD HH:MM:SS [LEVEL] module.name — message`); no client IPs; health checks silent.
6. **Added modules** — `cache`, `encryption`, `risk`, `health`, `signal` are part of the
   plan. `risk` is the pre-trade gate, disabled by default.

---

## Target directory structure (per `plan.md`)

```
lucid/
├── alembic/                        # DB migrations at repo root
│   └── versions/
│
├── src/
│   ├── modules/
│   │   ├── bus/                     # async event pub/sub
│   │   ├── cache/                   # in-memory TTL cache
│   │   ├── configs/                # layered config compilation
│   │   ├── db/                      # engine, session, models, repositories
│   │   │   ├── connection.py
│   │   │   ├── models/              # SQLAlchemy ORM, one file per domain
│   │   │   └── repositories/
│   │   ├── encryption/             # AES-256-GCM secrets
│   │   ├── logger/
│   │   ├── schedules/              # thin APScheduler layer
│   │   ├── authentication/         # JWT, first-run admin
│   │   ├── authorization/          # RBAC admin/trader/viewer
│   │   ├── backtrader/             # backtest + live bridge
│   │   ├── broker/                 # abstract broker + registry
│   │   ├── execution/              # signal → order pipeline
│   │   ├── risk/                    # pre-trade gate, disabled
│   │   ├── health/                 # /health/live,/ready
│   │   ├── price/                  # pipeline, storage, indicators, regime
│   │   ├── signal/                 # signal lifecycle
│   │   └── com/
│   │       ├── trading212/
│   │       ├── yahoofinance/
│   │       ├── zacks/
│   │       ├── finviz/
│   │       ├── barchart/
│   │       ├── tradingview/
│   │       ├── git/                # strategy repo sync
│   │       ├── claude/             # DISABLED placeholder
│   │       └── telegram/           # DISABLED placeholder
│   │
│   ├── conf/
│   │   ├── default.yml             # non-sensitive system defaults
│   │   └── schema.py               # Pydantic v2 config models
│   │
│   ├── api/
│   │   ├── v1/                     # auth, positions, signals, orders,
│   │   │                           #   settings, strategies, backtesting,
│   │   │                           #   prices, admin
│   │   └── main.py                 # create_app() factory
│   │
│   └── ui/                          # React + Vite + TS SPA
│
├── strategies/
│   ├── buy/                         # one-file buy strategies (flat)
│   └── sell/                        # one-file sell strategies (flat)
│
├── docs/
├── tests/
├── scripts/
├── docker/                          # Dockerfile, compose.yml, entrypoint.sh, prepare.sh
├── pyproject.toml
└── README.md
```

---

## Architecture principles (carried from the plans, aligned with `new.md`)

1. Every module declares its **required** and **optional** config keys — no implicit globals.
2. **Single-file strategies** — each buy/sell strategy is exactly one self-contained `.py`.
3. **Event-driven core** — modules talk through `bus`, not cross-domain imports.
4. **Config is layered** — `default.yml` → asset-class → global → per-user (later wins).
5. **Secrets never in YML** — keys ending `_key`/`_token`/`_secret`/`_password` come from the
   encrypted DB store; `LUCID_ENCRYPTION_KEY`/`LUCID_JWT_SECRET`/`DATABASE_URL` are env vars only.
6. **Paper trading is first-class** — every order path respects a `paper_mode` flag.
7. **Asset class is always explicit** — no function silently assumes equities.

---

# Milestones

Each milestone is independently testable and builds on the previous. Recommended order.
"DoD" = Definition of Done (acceptance criteria).

---

## M0 — Scaffolding & foundations

**Goal:** an installable, importable, empty-but-booting project skeleton.

Scope:
- Create the full directory tree above (empty `__init__.py` where needed).
- `pyproject.toml` with dependencies:
  - Runtime: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]>=2`, `asyncpg`,
    `alembic`, `pydantic>=2`, `pydantic-settings`, `apscheduler`, `backtrader`,
    `pandas`, `numpy`, `pyarrow`, `yfinance`, `httpx`, `cryptography`, `pyjwt`,
    `passlib[bcrypt]`, `pyyaml`.
  - Dev/test: `pytest`, `pytest-asyncio`, `aiosqlite`, `ruff`.
- `pyproject.toml` sets `asyncio_mode = "auto"`.
- `src/conf/default.yml` (empty sections stub) + `src/conf/schema.py` (Pydantic root model).
- `src/modules/logger/` — plain-text logger (see Open decision #2), format
  `YYYY-MM-DD HH:MM:SS [LEVEL] module.name — message`; no client IPs.
- `src/api/main.py` — `create_app()` returning a FastAPI app that boots with zero routes.
- `docker/` skeleton files (empty/stub for now).
- `README.md` stub.

**DoD:**
- `pip install -e .` succeeds.
- `python -c "from src.api.main import create_app; create_app()"` runs without error.
- `pytest` collects 0 tests and exits 0.

**Depends on:** none.

---

## M1 — Database foundation

**Goal:** schema, migrations, connection layer, and a generic repository.

Scope:
- `src/modules/db/connection.py` — async engine + session factory.
  - Required: `database_url`. Optional: `pool_size`, `max_overflow`, `echo`.
- `src/modules/db/models/` — one file per domain. Tables (from plan data model):
  - `users` (roles admin/trader/viewer, `must_change_password`)
  - `credentials` (encrypted; `user_id = NULL` = global default)
  - `positions` (per-user, `(user_id, ticker)` unique, open/closed)
  - `orders` (per-user, linked to signals/positions)
  - `signals` (per-user; source + confidence + `asset_class`)
  - `signal_outcomes` (per-user; profitable after close?)
  - `daily_losses` (per-user; UTC calendar day)
  - `app_logs` (per-user)
  - `strategy_registry` (global; name, file_path, direction, is_builtin, version, description, last_scanned_at)
  - `user_config` (per-user; key/value + asset_class)
  - `price_watchlist` (global)
  - `price_fetch_log` (global)
- `alembic/` (repo root) — Alembic env wired to the models; initial migration `0001`.
- `src/modules/db/repositories/` — `BaseRepository` with
  `get_by_id`, `get_all`, `create`, `update`, `delete`, `paginate`; one repo per model.

**DoD:**
- `alembic upgrade head` creates all tables on a fresh Postgres.
- Unit tests (in-memory `aiosqlite`) cover BaseRepository CRUD + pagination.
- Every secret-bearing column is designed to hold ciphertext, never plaintext.

**Depends on:** M0.

---

## M2 — Security core (encryption, authentication, authorization)

**Goal:** secrets at rest, login, and role gating.

Scope:
- `src/modules/encryption/` — AES-256-GCM. Key from `LUCID_ENCRYPTION_KEY` env only.
  Optional key-rotation hook.
- `src/modules/authentication/` — JWT access + refresh tokens; password hashing (bcrypt).
  - Required: `LUCID_JWT_SECRET`, `token_expiry_minutes`. Optional: `refresh_token_expiry_days`.
  - **First-run:** if no users exist, allow creating the first admin without auth, then lock down.
  - `must_change_password` enforced on first login.
- `src/modules/authorization/` — RBAC with roles `admin` / `trader` / `viewer`
  (table from plans: admin=system settings+user mgmt, no trading; trader=trading+own creds;
  viewer=read + own password).
- **Credential cascade** (`get_credential(key, user_id)`):
  1. `use_default_credentials=true` → global credential
  2. user-specific credential
  3. fall back to global
  4. else raise `CredentialNotConfiguredError`

**DoD:**
- Encrypt→store→decrypt round-trip test.
- First-admin bootstrap + subsequent lockdown tested.
- Login issues valid access/refresh tokens; role helpers gate correctly.
- Credential cascade unit-tested for all four branches.

**Depends on:** M1.

---

## M3 — Config system

**Goal:** dynamic, layered config compiled from active modules + strategies.

Scope:
- `src/modules/configs/` — layered resolution, higher wins:
  1. `default.yml` → 2. asset-class DB → 3. global DB → 4. per-user DB.
  - Required: path to `default.yml`. Optional: `db_overrides_enabled` (default true).
- **Schema compilation:** load `default.yml`, scan active modules' declared schemas,
  read active buy/sell strategy `CONFIG_SCHEMA`, merge into one grouped schema, overlay DB values.
- **Secrets rule:** any `*_key`/`*_token`/`*_secret`/`*_password` never read from YML.
- `src/conf/schema.py` — Pydantic v2 models per config section.

**DoD:**
- Resolution-order test proves per-user overrides beat global beat asset-class beat default.
- Compiled-schema output changes when the active strategy changes.
- Attempting to place a secret in YML is rejected/ignored (test).

**Depends on:** M1, M2.

---

## M4 — Event bus + cache

**Goal:** the async backbone modules communicate over.

Scope:
- `src/modules/bus/` — async pub/sub; **one failing handler never blocks others**
  (exceptions caught per-handler). Optional: `max_queue_size`.
  - Events: `BuySignalEvent(ticker, confidence, reasoning, source, user_id, asset_class)`,
    `SellSignalEvent(… quantity_pct)`, `OrderFilledEvent`, `OrderRejectedEvent`, `PriceFetchedEvent`.
- `src/modules/cache/` — in-memory TTL cache (dedup windows, redundant-fetch avoidance).
  Optional: `default_ttl_seconds`, `max_entries`.

**DoD:**
- Publish/subscribe test with multiple handlers; a raising handler is isolated.
- Cache TTL expiry + max-entries eviction tested.

**Depends on:** M0.

---

## M5 — Broker interface + Trading212 connector

**Goal:** place orders (paper first) through a pluggable broker.

Scope:
- `src/modules/broker/` — abstract interface + registry (one **active broker per user**,
  registered per asset class).
  - Interface: `place_market_order`, `get_positions`, `get_account_summary`, `cancel_order`.
  - Required: `broker_name`. Optional: `paper_mode` (default **true**).
- `src/modules/com/trading212/` — single-file REST client with retry-with-backoff + timeout.
  Optional per-connector circuit breaker (not system-wide).
  - Required: `api_key`, `base_url`. Optional: `timeout_seconds`, `retry_attempts`.

**DoD:**
- Paper `place_market_order` returns a simulated fill without network.
- `get_positions` / `get_account_summary` mocked and tested.
- Registry resolves the correct broker for `(user_id, asset_class)`.

**Depends on:** M2 (credentials), M3 (config), M4 (events).

---

## M6 — `execution` pipeline + risk gate

**Goal:** turn signals into broker orders. The `execution` module makes no trading decisions — strategies decide, it executes.

Scope:
- `src/modules/execution/` — subscribes to the bus; **makes no trading decisions**, executes what a strategy produced.
  - **Buy flow:** receive `BuySignalEvent` → per-ticker `asyncio.Lock` (dedup) →
    check existing open position → compute quantity (`fixed_usd` | `pct_portfolio` | `half_kelly`)
    → if risk enabled run gate → place order via broker.
  - **Sell flow:** receive `SellSignalEvent` → look up position →
    compute quantity (full or `quantity_pct` partial) → if risk enabled run gate → place order.
- `src/modules/risk/` — pre-trade gate, **disabled by default** (`risk.enabled=false`);
  a shell that can be toggled per-user via DB config. Hard limits when on:
  `max_single_trade_usd`, `max_daily_buy_usd`, `max_open_positions`, `max_position_pct`.

**DoD:**
- Buy/sell flows tested end-to-end against a mocked broker.
- Per-ticker lock prevents duplicate concurrent buys (test).
- Partial sell via `quantity_pct` tested.
- Risk gate: when disabled it's a no-op; when enabled it blocks over-limit orders (both tested).

**Depends on:** M4, M5.

---

## M7 — Price system

**Goal:** fetch, store, and analyze OHLCV.

Scope:
- `src/modules/price/`
  - `pipeline.py` — `run_daily`, `run_intraday`, `run_backfill` (watchlist-driven).
    Required: `storage_path`. Optional: `intraday_interval`, `backfill_days`.
  - `storage.py` — Parquet read/write at `/data/prices/`.
  - `indicators.py` — **pure functions** (RSI, MACD, ATR, Bollinger Bands, SMA 50/200,
    EMA, volume z-score, momentum); no DB, no network.
  - `regime.py` — `detect(benchmark="SPY") → bull|bear|neutral` from 50d vs 200d SMA.
- `src/modules/com/yahoofinance/` — yfinance wrapper returning normalized OHLCV.
- Publishes `PriceFetchedEvent`; updates `price_fetch_log`.

**DoD:**
- Fetch (mocked) → write Parquet → read back identical frame.
- Each indicator has a unit test against a known fixture.
- Regime detection tested for all three outcomes.
- Market-hours awareness per asset class (don't fetch/trade off-hours).

**Depends on:** M1, M4.

---

## M8 — Signal lifecycle

**Goal:** persist and de-duplicate signals; track outcomes.

Scope:
- `src/modules/signal/` — store `BuySignalEvent`/`SellSignalEvent` to DB; dedup within a
  configurable window (uses `cache`); mark signals acted-on/blocked; record
  `signal_outcomes` after a position closes (profitable?).

**DoD:**
- Duplicate signal inside the window is suppressed; outside it passes (test).
- Outcome row written on position close with correct P/L sign (test).

**Depends on:** M1, M4, M6.

---

## M9 — Scheduling

**Goal:** run recurring jobs safely.

Scope:
- `src/modules/schedules/` — thin APScheduler layer: register named jobs,
  hard timeout per task (default 5 min via `asyncio.wait_for`), `max_instances=1`,
  `coalesce=True`; expose job list + last-run status for the admin UI.
- Register jobs: poll positions, `price.run_daily`/`run_intraday`, strategy scan, git sync.

**DoD:**
- A job exceeding its timeout is cancelled and logged (test).
- Overlapping triggers coalesce; only one instance runs (test).
- Job list + last-run status queryable.

**Depends on:** M6, M7 (jobs to schedule).

---

## M10 — Strategy registry + single-file strategies

**Goal:** discover, register, and run one-file strategies.

Scope:
- `strategies/buy/` and `strategies/sell/` — flat, one `.py` per strategy.
  Each file exports:
  - `STRATEGY_NAME: str`, `STRATEGY_VERSION: str`
  - `CONFIG_SCHEMA: dict` (`{"key": {"type","default","required"}}`)
  - `async def run(context: StrategyContext) -> BuySignalEvent | None` (buy)
    / `-> SellSignalEvent | None` (sell)
- `StrategyContext` provides `ticker`, `position`, `price_data`, `config`, `asset_class`,
  `user_id`, and access to `price.indicators` / `price.regime`.
- **Scanner** upserts each discovered file into `strategy_registry`; runs at startup,
  on a daily job, and via `POST /api/v1/strategies/scan`.
- Per-user `active_buy_strategy` / `active_sell_strategy`; `decisions` loads the active
  strategy for the requesting user at runtime; switching it changes the compiled config view.
- Built-ins: `strategies/buy/trend_follow.py`, `strategies/sell/trailing_stop.py`
  (ATR trailing stop + profit-taking at configurable levels).

**DoD:**
- Scan discovers files and upserts registry rows (name, version, direction, is_builtin).
- Changing active strategy changes compiled settings schema (test).
- Built-in strategies each have a counterpart test in `tests/strategies/`.

**Depends on:** M3 (config compile), M4, M6, M7.

---

## M11 — Backtrader integration

**Goal:** backtest historical bars and bridge a live strategy to the bus.

Scope:
- `src/modules/backtrader/`
  - **Backtest mode:** run a `bt.Strategy` against historical Parquet bars → metrics.
  - **Live bridge:** run a strategy live; translate broker orders into
    `BuySignalEvent` / `SellSignalEvent` published to the bus.
  - Required: `strategy_class`, `mode` (`backtest`|`live`). Optional: `initial_cash`,
    `commission`, `lookback_days`.

**DoD:**
- Backtest against a fixture Parquet returns deterministic metrics (test).
- Live bridge emits the expected events for a scripted strategy (test).

**Depends on:** M4, M7.

---

## M12 — Remaining connectors, git sync, disabled placeholders

**Goal:** finish `com/` and strategy syncing.

Scope:
- `src/modules/com/{zacks,finviz,barchart,tradingview}/` — one file each; declare
  `REQUIRED_CONFIG`/`OPTIONAL_CONFIG`; return normalized OHLCV/metadata.
- `src/modules/com/git/` — pull the strategy repo to sync files into `strategies/buy|sell/`;
  store the commit hash as strategy version. On-demand + optional scheduled pull.
- `src/modules/com/claude/` — **DISABLED** placeholder (importable, inert).
- `src/modules/com/telegram/` — **DISABLED** placeholder (no dispatcher).

**DoD:**
- Each connector returns a normalized shape against a mocked response (test).
- Git sync pulls and the scanner picks up new files (test with a local temp repo).
- Placeholders import cleanly and are called by nothing active (test).

**Depends on:** M3, M10.

---

## M13 — API layer

**Goal:** expose everything under `/api/v1/` and add health probes.

Scope:
- `src/api/main.py` — `create_app()` mounts `/api/v1` and serves the React bundle at `/`
  (SPA catch-all).
- `src/api/v1/`:
  `auth.py`, `positions.py` (+ `POST /positions/sync`), `signals.py`, `orders.py`,
  `settings.py` (`GET /settings/schema`, `GET/POST /settings`), `strategies.py`
  (`GET`, `POST /scan`, `PATCH /{name}/activate`), `backtesting.py` (`POST /run`),
  `prices.py` (`GET /{ticker}`, `POST /backfill`), `admin.py` (`GET/POST /users`).
- `src/modules/health/` — `GET /health/live`, `GET /health/ready` (DB reachable);
  **trace-level logging only** — never in normal logs.
- All routes auth-gated by role; access logging suppressed (no client IPs).

**DoD:**
- OpenAPI docs list all routes; auth/role gating enforced (tests).
- `/settings/schema` returns the compiled schema for `(user_id, asset_class)`.
- `/positions/sync` reconciles broker vs local DB (test with mocked broker).
- Health endpoints work and emit nothing to normal logs.

**Depends on:** M2, M3, M5–M11.

---

## M14 — UI (React + Vite + TS)

**Goal:** modular SPA served by FastAPI.

Scope:
- `src/ui/` — Vite + React + TypeScript. `src/{components,pages,hooks,api,types}`.
- Pages (one file per route): dashboard, positions, signals, orders/history,
  strategies, settings, prices, admin/users, backtesting, login.
- **Settings page is fully schema-driven** — renders the compiled schema from
  `GET /api/v1/settings/schema`; no hardcoded forms. Switching buy/sell strategy changes
  visible fields.
- Typed fetch wrappers in `src/ui/src/api/` for `/api/v1`.

**DoD:**
- `vite build` produces a static bundle FastAPI serves at `/`.
- Login → dashboard → positions/signals render against the live API.
- Changing active strategy re-renders the settings form fields.

**Depends on:** M13.

---

## M15 — Docker, hardening & build pipeline

**Goal:** single hardened container; tests gate the build.

Scope:
- `docker/Dockerfile` — multi-stage: build the React bundle, then the Python image;
  **run the full test suite during build** (build fails on any test failure).
- `docker/compose.yml` — single container, single port (default **8686**); hardened:
  non-root user `lucid` uid **8686**, `read_only: true`, `cap_drop: [ALL]`,
  `no-new-privileges:true`, `tmpfs: /tmp,/run`; volumes `lucid_data → /data`,
  `strategies/ → /strategies`.
- `docker/entrypoint.sh` — `alembic upgrade head` → scan+upsert built-in strategies →
  `uvicorn` with `--no-access-log`.
- `docker/prepare.sh` — host prep (rootless Podman / SELinux `chown`/`chcon`).
- **NIC binding** — `BIND_IFACE` / `BIND_IP` applied at process start to lock outbound
  traffic (VPN bypass prevention).
- Env vars: `DATABASE_URL`, `LUCID_ENCRYPTION_KEY`, `LUCID_JWT_SECRET`, optional
  `BIND_IFACE`/`BIND_IP`.

**DoD:**
- `docker compose build` runs tests and fails on a failing test.
- `docker compose up` boots; API + UI reachable on 8686; migrations applied; built-ins registered.
- Container runs non-root with the hardening flags above.

**Depends on:** M13, M14.

---

## M16 — Carry-over features audit + docs

**Goal:** verify legacy parity and document.

Legacy features to confirm present (mapped to milestones):

- [x] Per-ticker async lock — M6
- [x] NIC binding (`BIND_IFACE`/`BIND_IP`) — M15
- [x] First-run admin bootstrap — M2
- [x] `must_change_password` on first login — M2
- [x] Signal outcome tracking — M8
- [x] Daily loss tracking (UTC day) — M1 (`daily_losses`) + M6 (risk gate)
- [x] Partial sells (`quantity_pct`) — M6
- [x] Position sync from broker — M13 (`/positions/sync`)
- [x] Paper trading at order level — M5
- [x] Market-hours gate per asset class — M7 (asset-class aware; hours hook in price)
- [x] Logging: plain text, no client IPs — M0
- [x] Access-log suppression (no client IPs) — M13/M15
- [x] Trailing stop w/ ATR + profit-taking — M10

Docs:
- `docs/` — architecture overview, module reference, config guide, deployment,
  strategy authoring guide.
- `README.md` — quickstart, env vars, build/run.

**DoD:**
- Every checklist item verified by a test or documented manual step.
- Docs cover setup, config, strategy authoring, and deployment.

**Depends on:** all prior.

---

## Testing strategy (applies to every milestone)

- Tests run during `docker build`; build fails on any failure.
- In-memory `aiosqlite` for fast unit tests; a Postgres container for integration tests.
- Mock **all** external APIs — no real network calls in tests.
- `pytest-asyncio` with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed).
- Coverage priorities: `execution` pipeline, config resolution/compilation, credential
  cascade, strategy loading, risk gate (even when disabled).
- `tests/` mirrors `src/`; strategy tests in `tests/strategies/`.

---

## Decisions settled by `plan.md`

These were previously open; `plan.md` settles them:

1. **Strategy layout** — flat one-file strategies in `strategies/buy/` and `strategies/sell/`
   (no subdirectories).
2. **Logging format** — plain text (`YYYY-MM-DD HH:MM:SS [LEVEL] module.name — message`),
   no client IPs, health checks silent.
3. **DB layout** — consolidated `src/modules/db/` (`connection.py`, `models/`,
   `repositories/`) + migrations at repo root `alembic/`.
4. **React build delivery** — build inside the Docker image, served as a static bundle.
5. **Paper-trading scope** — per-user `paper_mode` flag in config (default true).

---

## Suggested critical path

```
M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10 → M11 → M12 → M13 → M14 → M15 → M16
```

M4 (bus) can start in parallel with M2/M3. M7 (price) can start once M1/M4 are done, in
parallel with M5/M6. UI (M14) only needs the API (M13) stable.
