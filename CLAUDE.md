# CLAUDE.md

Guidance for Claude Code (and other AI agents) working in this repository.

## What this is

Python 3.12 + FastAPI backend, React (Vite)
frontend, PostgreSQL, Parquet price storage, single hardened Docker container on
port 8686. See [docs/architecture.md](docs/architecture.md) for the full layer/module
map and request→order flow diagram, and [README.md](README.md) for env vars.

## THE hard rule: testing is Docker-only, no exceptions

**Never run `pytest`, `npm`, `python3 -c "..."`, or any other code on the local
host** — not even a throwaway one-liner to check a date/timezone/math fact. Verify
everything by running:

```bash
docker build -f docker/Dockerfile -t lucid-test .
```

from the repo root. This single build:
1. Builds the React UI (`npm run build` — no separate `tsc` type-check gate; unused
   imports/vars won't fail the build even though `tsconfig` has `noUnusedLocals`).
2. Installs the Python package and runs `python -m pytest -q` as a `RUN` step.

A build failure (either stage) is a test failure — full stop. There is no ruff/lint
gate in the pipeline either; `python -m pytest -q` is the only backend gate. If
unsure about a fact needed to write an assertion (e.g. "is this timestamp within
market hours"), write the test/mock and let the Docker pytest output be the
verification, don't try to reason it out by executing code locally.

This rule is enforced by [.github/instructions/generic.instructions.md](.github/instructions/generic.instructions.md).

## Architecture at a glance

```
React SPA (src/ui) → FastAPI (src/api, /api/v1/*) → AppContext (composition root)
                                                        │
                        ┌───────────────┬───────────────┼───────────────┐
                        ▼               ▼               ▼               ▼
                 modules/configs   modules/bus   modules/execution  modules/broker
                 (layered schema)  (pub/sub)      (order pipeline)   modules/price
```

- **Modules communicate over `modules/bus`** (async pub/sub, domain events), not
  cross-domain imports.
- **Config is layered**: `default.yml` → asset-class-scoped DB → global DB →
  per-user DB (later wins) — see `src/modules/configs/__init__.py`.
- **Strategies are single files** in `strategies/buy/*.py` / `strategies/sell/*.py`,
  dynamically loaded (see `src/modules/strategy/loader.py`). Each declares
  `STRATEGY_NAME`, `run(context) -> StrategyDecision`, and optional module-level
  attributes: `FEATURES`, `EXTERNAL_SOURCES`, `USES_WATCHLIST`, `CONFIG_SCHEMA`. Read
  [strategies/README.md](strategies/README.md) before adding/modifying one.
- **Secrets never in YAML/config** — only in the encrypted credential store
  (`src/modules/encryption`, AES-256-GCM, key from `LUCID_ENCRYPTION_KEY` only).
- **Paper trading is first-class** (`broker.paper_mode`, default `true`).
- **Asset class is always explicit** (`AssetClass` enum: equity/commodity/crypto/fx)
  — a user can hold positions and use different brokers across multiple asset
  classes simultaneously; don't write code that assumes "one asset class per user".
- **No pre-trade risk gate exists** (deliberately removed, see
  `docs/risk-gate-design.md` — documented but not implemented, don't re-add without
  asking).

## Request → order flow

```
scheduler.run_strategies (sell: per trader's open positions · buy: per watchlist
ticker, or per strategy-discovered candidate if USES_WATCHLIST=False)
  → active buy/sell strategy .run(StrategyContext) → StrategyDecision
    → BuySignalEvent / SellSignalEvent published on the bus
      → ExecutionEngine.handle_buy/handle_sell (src/modules/execution)
        → per-(user,ticker) lock · position check · sizing · broker order
          → OrderFilledEvent / OrderRejectedEvent
```

Every strategy evaluation is recorded as a `StrategyDecision` (acted + human-readable
`reasoning`), deduped so a row is only inserted when the outcome actually changes —
see `TradingRuntime._record_decision` in [src/api/runtime.py](src/api/runtime.py).

## Key gotchas (read before touching related code)

- **Cross-session ORM objects**: `get_current_user`/`require_permission`
  (`src/api/deps.py`) load the `User` on their own short-lived DB session, separate
  from the route's `session: AsyncSession = Depends(get_session)`. Never pass that
  `user` into a repository `.update()` on the route's session — refetch it first
  (`await UserRepository(session).get_by_id(user.id)`). Same rule applies to any ORM
  object crossing a `db.transaction()` block boundary — always refetch by id.
- **Barrel files**: `src/modules/db/repositories/__init__.py` and
  `src/modules/db/models/__init__.py` re-export every repo/model. When
  adding/removing one, grep both — easy to miss.
- **Market-hours gating is real wall-clock time**: `src.modules.schedules.
  market_hours.is_open(region, now=None)` defaults to the actual current time.
  Any test that calls `TradingRuntime.run_strategies()` (or otherwise reaches the
  buy/sell evaluation loops) must `monkeypatch.setattr(market_hours, "is_open", ...)`
  unless it's specifically testing market-hours behavior — otherwise the test's
  pass/fail depends on what time of day the Docker build happens to run.
- **Per-asset-class isolation**: broker resolution, positions, and price fetching
  are scoped by `asset_class`. When writing code that touches "all of a user's
  positions" (e.g. reconciliation/sync logic), check whether it should be filtered
  by `asset_class` or is intentionally cross-asset-class (sell-strategy evaluation
  intentionally looks at *every* open position regardless of asset class; broker
  sync must *not* touch other asset classes' positions).
- **Alembic migrations vs. ORM models can drift**: a hand-written migration (not
  autogenerated) for a model using `TimestampMixin` must explicitly match
  `server_default=sa.text("now()")` on `created_at`/`updated_at` — the sqlite-backed
  pytest suite builds its schema straight from `Base.metadata`, so this class of
  drift is invisible to the whole test suite and only bites in real Postgres.
- **`configure_logging()`-style "idempotent configure" functions**: never gate
  mutable state (e.g. log level) behind the same one-time flag as one-time setup
  (e.g. handler registration) if anything else in the codebase might trigger an
  earlier implicit call with different/default arguments.
- **Dynamic strategy loading** (`importlib.util`): always set
  `sys.modules[name] = mod` before `exec_module(mod)` if the loaded file might use
  `@dataclass`/postponed annotation evaluation.

## Directory layout

- `src/api/` — FastAPI routes (`v1/*.py`), `context.py` (composition root
  `AppContext`), `runtime.py` (`TradingRuntime`: scheduler + strategy evaluation).
- `src/modules/` — reusable domain modules (bus, db, configs, broker, execution,
  price, signal, strategy, authentication, authorization, encryption, schedules,
  backtrader, com/* external connectors, health, netbind).
- `src/conf/` — `default.yml` (non-secret defaults) + `schema.py` (Pydantic models
  driving both validation and the dynamic Settings-UI schema).
- `src/scripts/` — one-off/startup scripts (`sync_algorithms.py` runs at container
  start, `migrate_legacy_prices.py`, `ensure_database.py`).
- `src/ui/src/` — React + Vite SPA: `pages/`, `components/`, `hooks/`, `lib/`, `api/`.
- `strategies/buy/`, `strategies/sell/` — built-in single-file strategies, baked into
  the image (`BUILTIN_STRATEGIES_ROOT`), seeded into the writable, ephemeral
  `STRATEGIES_ROOT` at startup; optionally overlaid by git-synced custom strategies
  (`EXT_STRATEGIES`, see "Algorithm git sync" in docs/architecture.md).
- `alembic/` — DB migrations (`alembic upgrade head` against real Postgres; not
  exercised by the sqlite-based test suite).
- `tests/` — one file per module/domain, `tests/strategies/` for built-in strategies.
- `docker/` — `Dockerfile` (build+test gate), `compose.yml`, `entrypoint.sh`.

## Conventions

- Comments: brief, single-line, state what the code can't show on its own — no
  multi-paragraph doc comments. Detailed rationale lives in `docs/*.md` or is left
  out entirely.
- Don't add features/refactors/guardrails beyond what's asked. This codebase has a
  documented list of deliberately-deferred features — see `tmp/missing.md` for the
  decision log before adding risk gates, circuit breakers, new connectors, etc.
- Git: never run write/history-modifying git commands (`add`, `commit`, `push`,
  `reset`, `rebase`, ...) on behalf of the user — leave changes in the working tree
  for review. Read-only git commands (`status`, `log`, `diff`, `show`) are fine.
