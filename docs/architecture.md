# Lucid — Architecture

Event-driven trading platform. Python + FastAPI backend, React (Vite) frontend,
PostgreSQL, Parquet price storage, single hardened Docker container on port 8686.

## Layers

```
                         ┌──────────────┐
   React SPA  ─────────▶ │  FastAPI     │  /api/v1/*  +  /health/*  +  SPA at /
   (src/ui)              │  (src/api)   │
                         └──────┬───────┘
                                │ AppContext (composition root)
        ┌───────────────────────┼───────────────────────────────┐
        ▼                       ▼                                ▼
   modules/configs        modules/bus  ◀──────────────  modules/execution
   (layered schema)       (pub/sub)      Buy/Sell events  (order pipeline)
        │                       │                                │
        ▼                       ▼                                ▼
   src/db (models)        modules/signal                  modules/broker
   modules/db (repos)     modules/signal                  modules/broker
        │                                                        │
        ▼                                                        ▼
   PostgreSQL                                             modules/price (Parquet,
                                                          indicators, regime)
```

## Core principles

1. Every module declares required/optional config keys — no implicit globals.
2. Single-file strategies in `strategies/buy` and `strategies/sell`.
3. Modules communicate over `modules/bus`, not cross-domain imports.
4. Config is layered: `default.yml` → asset-class → global → per-user (later wins).
5. Secrets never in YAML — encrypted in the DB via `modules/encryption`.
6. Paper trading is first-class (`broker.paper_mode`, default true).
7. Asset class is always explicit (`AssetClass` enum).

## Request → order flow

```
scheduler.run_strategies (per trader, per watchlist ticker)
  → active buy/sell strategy .run(StrategyContext)
    → BuySignalEvent / SellSignalEvent published on the bus
      → ExecutionEngine.handle_buy/handle_sell
        → per-ticker lock · position check · sizing · broker order
          → OrderFilledEvent / OrderRejectedEvent
```

## Module map (`src/modules`)

| Module | Responsibility |
|---|---|
| `bus` | Async pub/sub, isolated handlers, domain events |
| `cache` | In-memory TTL cache (dedup, fetch throttling) |
| `configs` | Layered resolution + dynamic schema compilation |
| `db` | Engine/session, ORM models live in `src/db/models` via `modules/db` |
| `encryption` | AES-256-GCM secrets + credential cascade |
| `authentication` | JWT tokens, password hashing, first-run admin |
| `authorization` | RBAC: admin / trader / viewer |
| `broker` | Abstract broker + registry + paper broker |
| `execution` | Signal → order pipeline (no decisions) |
| `price` | Pipelines, Parquet storage, indicators, regime |
| `signal` | Signal lifecycle: store, dedup, outcomes |
| `schedules` | Thin APScheduler wrapper with timeouts |
| `backtrader` | Backtesting + live bridge to the bus |
| `strategy` | Context, single-file loader, registry service |
| `health` | Liveness/readiness probes (silent in logs) |
| `netbind` | Outbound NIC binding (VPN bypass prevention) |
| `com/*` | External connectors (trading212, yahoo, zacks, …) |

## Algorithm git sync

`STRATEGIES_ROOT` (what `modules/strategy/loader` actually scans) is a writable but
ephemeral directory — a tmpfs mount in production, empty on every container start —
merged from two sources, in order, every time the app starts and on every
`git_sync.interval_minutes` tick:

1. **Built-ins**: seeded from `BUILTIN_STRATEGIES_ROOT` (`/app/strategies`, baked into
   the image, never mounted over) via `modules.strategy.seed_missing_strategies` —
   copy-if-absent, so it never clobbers a file already deployed by step 2.
2. **Git-synced**: `com/git.GitSync` clones/pulls the configured repo
   (`git_sync.repo_url`, admin-only system setting) into `EXT_STRATEGIES` — a mounted
   volume, never executed from directly — then `deploy_strategies` copies its
   `buy/`/`sell/` files into `STRATEGIES_ROOT`, always overwriting on conflict.

```
/app/strategies (built-in, image-baked) ──seed (copy-if-absent)──┐
                                                                   ▼
git repo ──sync──▶ EXT_STRATEGIES (staging, mounted volume) ──deploy (overwrite)──▶ STRATEGIES_ROOT (served by the app)
```

This runs once at container startup (`src/scripts/sync_algorithms.py`, invoked from
`docker/entrypoint.sh` before the app starts) and again on `git_sync.interval_minutes`
via the scheduler, so the app never runs code straight out of the image layer or the
staging mount — only out of the merged `STRATEGIES_ROOT`.
