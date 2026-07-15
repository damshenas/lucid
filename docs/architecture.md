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
scheduler.run_strategies (sell: per trader's open positions · buy: per watchlist ticker)
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
| `authorization` | RBAC: admin / trader / analyst |
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
merged from two sources, in order:

1. **Built-ins**: seeded from `BUILTIN_STRATEGIES_ROOT` (`/app/strategies`, baked into
   the image, never mounted over) via `modules.strategy.seed_missing_strategies` —
   copy-if-absent, so it never clobbers a file already deployed by step 2.
2. **Git-synced**: `com/git.GitSync` runs `git pull` in `EXT_STRATEGIES` — a mounted
   volume that is expected to already be a git checkout with its remote/branch
   configured out-of-band on the host (not cloned by the app) — then
   `deploy_strategies` copies its `buy/`/`sell/` files into `STRATEGIES_ROOT`, always
   overwriting on conflict.

```
/app/strategies (built-in, image-baked) ──seed (copy-if-absent)──┐
                                                                   ▼
EXT_STRATEGIES (pre-cloned checkout) ──git pull──▶ (staged) ──deploy (overwrite)──▶ STRATEGIES_ROOT (served by the app)
```

This runs unconditionally at container startup (`src/scripts/sync_algorithms.py`,
invoked from `docker/entrypoint.sh` before the app starts) — best-effort, so a missing
or not-yet-provisioned `EXT_STRATEGIES` checkout is logged and skipped rather than
failing the boot. Beyond that, syncing is **on-demand only** — there is no recurring
schedule and no separate enable/disable setting. An admin triggers it any time via
`POST /api/v1/admin/git-sync` (the "Sync now" button in Settings > Service > Git
Sync); clicking it is itself the admin's consent. Either way,
the app never runs code straight out of the image layer or the staging mount — only
out of the merged `STRATEGIES_ROOT`.

## Deferred features (documented, not implemented)

A couple of features were deliberately designed but not built, per an explicit
product decision to document the design for a later call rather than build them now:

- [Risk gate design](risk-gate-design.md) — a pre-trade Guardian-style limit gate
  (single-trade cap, daily-buy cap, max open positions, drawdown halt). Today there is
  **no automated risk enforcement at all** on any order.
- [Daily P&L design](daily-pnl-design.md) — a daily realized-P&L aggregate table and
  dashboard equity/P&L chart. Today the Dashboard has no aggregate chart.

