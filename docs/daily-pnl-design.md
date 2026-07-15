# Daily P&L Aggregate & Dashboard Chart — Design (documented, not implemented)

Status: **not implemented**. The Dashboard page today shows live positions/orders/
signals but has no historical equity curve or daily realized-P&L chart. This document
describes a design for adding one, for a future decision on whether to build it.

## Proposed scope

A daily rollup job that aggregates each user's realized P&L (from closed positions/
sell fills) and portfolio equity snapshot into one row per (user, day), plus a
Dashboard chart reading from it.

## Data model

```python
class DailyStats(Base, TimestampMixin):
    __tablename__ = "daily_stats"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    id: Mapped[int]
    user_id: Mapped[int]          # FK -> users.id
    day: Mapped[date]
    realized_pnl_usd: Mapped[float]   # sum of (sell_price - avg_cost) * qty for the day
    equity_usd: Mapped[float]         # end-of-day portfolio equity (cash + holdings)
    trade_count: Mapped[int]          # number of fills that day, for context
```

## Where it's populated

Two options, in increasing order of complexity:

1. **Scheduled rollup job** (simplest): a new daily job (`register_jobs()` in
   `src/api/runtime.py`, alongside `price_daily`) that, once a day per active trader,
   computes yesterday's realized P&L from `orders`/`positions` and today's equity from
   `Broker.get_account_summary()`, and upserts one `DailyStats` row.
2. **Incremental on every fill** (more accurate intraday, more code): increment
   `realized_pnl_usd` directly inside `ExecutionEngine.handle_sell` when a sell fills,
   in the same transaction as the order/position update — avoids a nightly
   recomputation but means `DailyStats` needs to be touched from the hot execution
   path rather than staying purely a reporting-side concern.

Recommend starting with option 1 (scheduled job) — it keeps `ExecutionEngine` free of
reporting concerns and is good enough for a daily chart (not an intraday one).

## API surface (proposed)

```
GET /api/v1/positions/daily-stats?days=90
  -> [{ day, realized_pnl_usd, equity_usd, trade_count }, ...]
```

Gated on `Permission.view_trading` (same as other Dashboard data), scoped to the
requesting user (no separate admin-wide report — that's covered by the price/fetch
reports already implemented under `/api/v1/admin/reports/*`).

## Frontend

Two chart additions to `pages/Dashboard.tsx`:

- **Equity curve**: an area/line chart of `equity_usd` over time.
- **Daily realized P&L**: a bar chart of `realized_pnl_usd` per day, colored by sign
  (green/positive, rose/negative — matching the existing Badge tone conventions used
  elsewhere in the UI).

No new charting library is currently a dependency — would need to either add one
(e.g. `recharts`) or hand-roll a minimal SVG chart component, consistent with the
existing "keep dependencies lean" pattern in `src/ui`.

## Explicitly out of scope for this design

- No intraday equity chart — daily granularity only, matching the rollup job's cadence.
- No admin-wide aggregate view across all users — this is a per-user Dashboard feature.
- No backfill tooling for historical data predating the rollup job's introduction —
  the chart would simply start from whenever `DailyStats` starts being populated.
