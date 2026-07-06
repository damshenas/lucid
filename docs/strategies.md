# Lucid — Strategy Authoring

See **`strategies/README.md`** for the full, example-driven authoring guide (aimed at
anyone — human or LLM — writing a new strategy file). This page is the shorter
reference version.

Each strategy is a **single `.py` file**, flat in `strategies/buy/` or `strategies/sell/`.
No subdirectories. Files are discovered at startup and via
`POST /api/v1/strategies/scan` (manual rescan) — there is no recurring scan job.

## Required exports

```python
STRATEGY_NAME: str        # unique identifier
STRATEGY_VERSION: str     # semver or git hash
CONFIG_SCHEMA: dict       # {"key": {"type": ..., "default": ..., "required": bool}}

async def run(context) -> StrategyDecision   # both strategies/buy/ and strategies/sell/
```

`StrategyDecision` (see `src/modules/strategy/context.py`) always carries a
human-readable `reasoning` string — whether or not the strategy decided to act — plus
the resulting event when it did:

```python
@dataclass(slots=True)
class StrategyDecision:
    acted: bool
    reasoning: str
    event: BuySignalEvent | SellSignalEvent | None = None  # required when acted=True
```

This reasoning is what powers each active strategy's "Decisions" list in the UI (see
pages/StrategyDetail.tsx) — return a real explanation for every branch, not just the
acted-on case.

Optional module attributes: `STRATEGY_DESCRIPTION: str`, `FEATURES: list[str]` (UI
feature tags, e.g. `["signals"]` to also show the signals feed on the strategy's page),
`EXTERNAL_SOURCES: list[str]` (third-party ratings — e.g. `["zacks"]` — to fetch before
every `run()`; see "External signal sources" below).

"Native" vs "custom" (shown as a tag in the UI) is derived automatically from actual
file origin, not a self-declared flag: a file only counts as native if it's
byte-identical to the one shipped in `BUILTIN_STRATEGIES_ROOT`. Anything a git sync
deploys into `STRATEGIES_ROOT` — including a same-named override of a built-in — is
"custom", since the deploy step always overwrites on conflict.

## StrategyContext

| Field | Meaning |
|---|---|
| `ticker` | symbol under evaluation |
| `user_id` | owning user |
| `asset_class` | `equity` / `commodity` / `crypto` / `fx` |
| `config` | resolved config dict for the user |
| `price_data` | pandas OHLCV DataFrame (lowercase columns) |
| `position` | `PositionView(ticker, quantity, avg_price)` or `None` |
| `external_signals` | `list[ExternalSignal]` — populated only for sources declared via `EXTERNAL_SOURCES`; `[]` otherwise |

`context.strategy_config(STRATEGY_NAME)` returns your strategy's config sub-dict. The keys
in `CONFIG_SCHEMA` are folded into the user's Settings form automatically.

## Example (buy)

```python
from src.modules.bus import BuySignalEvent
from src.modules.price.indicators import compute_snapshot
from src.modules.strategy.context import StrategyContext, StrategyDecision

STRATEGY_NAME = "trend_follow"
STRATEGY_VERSION = "1.0.0"
CONFIG_SCHEMA = {"rsi_max": {"type": "float", "default": 70.0, "required": False}}


async def run(context: StrategyContext) -> StrategyDecision:
    df = context.price_data
    if df is None or len(df) < 200:
        return StrategyDecision(acted=False, reasoning="not enough stored bars yet")
    cfg = context.strategy_config(STRATEGY_NAME)
    snap = compute_snapshot(df)
    if snap.sma_50 and snap.sma_200 and snap.sma_50 > snap.sma_200:
        if snap.rsi is None or snap.rsi < float(cfg.get("rsi_max", 70.0)):
            reasoning = f"SMA50 ({snap.sma_50:.2f}) > SMA200 ({snap.sma_200:.2f})"
            return StrategyDecision(
                acted=True,
                reasoning=reasoning,
                event=BuySignalEvent(
                    ticker=context.ticker, user_id=context.user_id,
                    source=STRATEGY_NAME, asset_class=context.asset_class,
                    reasoning=reasoning,
                ),
            )
    return StrategyDecision(acted=False, reasoning="no uptrend or RSI overbought")
```

Sell strategies return a `SellSignalEvent` in `StrategyDecision.event`; set
`quantity_pct` for a partial exit (omit or `None` for a full exit).

## Indicators & regime

Import pure helpers directly:

```python
from src.modules.price.indicators import rsi, macd, atr, bollinger, compute_snapshot
from src.modules.price import regime
regime.detect(benchmark_df)  # "bull" | "bear" | "neutral"
```

## Activation

Each user has an active buy and sell strategy (config keys
`strategy.active_buy_strategy` / `strategy.active_sell_strategy`). Set them via
Settings > Strategy or `PATCH /api/v1/strategies/{name}/activate?direction=buy`.
Once active, its decision log is available in the sidebar (see
`GET /api/v1/strategies/{name}/decisions` and pages/StrategyDetail.tsx).

Activating a strategy doesn't mean every ticker gets evaluated the same way — buy and
sell deliberately use different ticker sources (see `TradingRuntime.run_strategies` in
`src/api/runtime.py`): a **sell** strategy runs over every ticker the user has an
**open position** in (no configuration needed — the position itself is the
universe), while a **buy** strategy runs over the shared **price watchlist**
(`/api/v1/prices/watchlist`) since deciding what to *consider* buying requires a
curated candidate list. An empty watchlist means buy strategies never fire; it has no
effect on sell strategies.

## External signal sources

A strategy can declare `EXTERNAL_SOURCES = ["zacks", "tradingview"]` to have the
runtime fetch normalized third-party ratings (Finviz/TradingView/Zacks/Barchart — see
`src/modules/signal/sources.py`) before each `run()`, available via
`context.external_signals` / `context.external_signal(name)`. A source only
participates once its credentials are configured (`/api/v1/credentials`); check
status with `GET /api/v1/signals/sources` or test on demand with
`POST /api/v1/signals/sources/check`.

## Distribution via git

User strategies can be committed to a strategy repo and synced by `modules/com/git`;
the commit hash becomes the strategy version.
```
