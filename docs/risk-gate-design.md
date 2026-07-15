# Risk Gate — Design (documented, not implemented)

Status: **not implemented**. Lucid currently has **no automated pre-trade risk
enforcement whatsoever** — any strategy or manual order can place a trade of any size,
any number of times, regardless of portfolio exposure. This document describes a
design for adding one back, for a future decision on whether/how much of it to build.

## Why this doc exists instead of code

An earlier iteration of Lucid had a "Guardian" risk gate; it was removed
(`alembic/versions/0003_remove_risk.py`) because the artificial trade limits
interfered with validating strategy/algorithm accuracy during testing. Re-adding
automated limits is deferred until there's a concrete need — this doc exists so the
design doesn't have to be re-derived from scratch when that need comes up.

## Proposed scope

A pre-trade check invoked from `ExecutionEngine.handle_buy` (and optionally
`handle_sell`/`place_manual_order`) before the broker order is placed, enforcing
**hard** limits (reject the order outright) — no soft/warn-only tier for the first
version, to keep the initial implementation simple:

| Limit | Config key (proposed) | Description |
|---|---|---|
| Single-trade cap | `risk.max_single_trade_usd` | Reject a buy whose sized `quantity * price` exceeds this. |
| Daily buy-volume cap | `risk.max_daily_buy_usd` | Sum of today's buy fills (per user) must stay under this. |
| Max open positions | `risk.max_open_positions` | Reject a new buy if the user already holds this many open positions. |
| Max position size | `risk.max_position_pct` | Reject a buy that would make one position exceed this % of portfolio equity. |
| Portfolio drawdown halt | `risk.max_drawdown_pct` | Block *all* new buys for a user once realized+unrealized drawdown from a rolling equity high exceeds this. |

All limits would be **off by default** (`risk.enabled: bool = False`) and only ever
gate *buys* — sells (which reduce risk) would never be blocked.

## Data model

A restart-safe ledger is needed for the daily-buy-volume cap and the drawdown halt to
survive a container restart mid-day:

```python
class DailyRiskLedger(Base, TimestampMixin):
    __tablename__ = "daily_risk_ledger"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    id: Mapped[int]
    user_id: Mapped[int]  # FK -> users.id
    day: Mapped[date]
    buy_volume_usd: Mapped[float]        # sum of today's buy fills
    equity_high_watermark: Mapped[float]  # rolling high for the drawdown check
```

Updated inside the same transaction as a filled buy order in
`ExecutionEngine.handle_buy`.

## Where it plugs in

```
ExecutionEngine.handle_buy
  ├─ (existing) dedup check, open-position check, sizing, quote
  ├─ NEW: RiskGate.check_buy(user_id, ticker, quantity, price, portfolio_value)
  │        -> raises RiskLimitExceeded(reason) if any hard limit trips
  │        -> reason is recorded via SignalService.mark_blocked, same as any
  │           other buy rejection (broker-rejected, no price, etc.)
  └─ (existing) place order, record position/order, mark signal acted
```

A `RiskGate` class (new module, `src/modules/risk/`) would take the same
`config_provider`/`db` shape `ExecutionEngine` already uses, so it's trivially
injectable and testable with the same patterns as `sizing.py`.

## Config schema (proposed)

```python
class RiskConfig(BaseModel):
    enabled: bool = False
    max_single_trade_usd: float = 5_000.0
    max_daily_buy_usd: float = 20_000.0
    max_open_positions: int = 20
    max_position_pct: float = 25.0
    max_drawdown_pct: float = 25.0
```

Added to `LucidConfig` in `src/conf/schema.py` the same way every other section is —
it would automatically surface in the schema-driven Settings UI with no separate
frontend work needed beyond a "Risk" section label.

## Explicitly out of scope for this design

- No soft/warn-only limit tier (matches the removed Guardian's *hard* limits only,
  not its soft ones) — can be added later if hard-only proves too blunt.
- No manual-order exemption — if built, `place_manual_order` should go through the
  same gate as a strategy-driven buy, since decision #4 (missing.md) didn't ask for an
  exception.
- No UI beyond the auto-generated Settings section — no dedicated risk dashboard.
