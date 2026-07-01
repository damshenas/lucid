# Lucid — Strategy Authoring

Each strategy is a **single `.py` file**, flat in `strategies/buy/` or `strategies/sell/`.
No subdirectories. Files are discovered at startup, on a daily job, and via
`POST /api/v1/strategies/scan`.

## Required exports

```python
STRATEGY_NAME: str        # unique identifier
STRATEGY_VERSION: str     # semver or git hash
CONFIG_SCHEMA: dict       # {"key": {"type": ..., "default": ..., "required": bool}}

async def run(context) -> BuySignalEvent | None   # in strategies/buy/
async def run(context) -> SellSignalEvent | None  # in strategies/sell/
```

Optional module attributes: `STRATEGY_DESCRIPTION: str`, `STRATEGY_BUILTIN: bool`.

## StrategyContext

| Field | Meaning |
|---|---|
| `ticker` | symbol under evaluation |
| `user_id` | owning user |
| `asset_class` | `equity` / `commodity` / `crypto` / `fx` |
| `config` | resolved config dict for the user |
| `price_data` | pandas OHLCV DataFrame (lowercase columns) |
| `position` | `PositionView(ticker, quantity, avg_price)` or `None` |

`context.strategy_config(STRATEGY_NAME)` returns your strategy's config sub-dict. The keys
in `CONFIG_SCHEMA` are folded into the user's Settings form automatically.

## Example (buy)

```python
from src.modules.bus import BuySignalEvent
from src.modules.price.indicators import compute_snapshot
from src.modules.strategy.context import StrategyContext

STRATEGY_NAME = "trend_follow"
STRATEGY_VERSION = "1.0.0"
STRATEGY_BUILTIN = True
CONFIG_SCHEMA = {"rsi_max": {"type": "float", "default": 70.0, "required": False}}


async def run(context: StrategyContext) -> BuySignalEvent | None:
    df = context.price_data
    if df is None or len(df) < 200:
        return None
    cfg = context.strategy_config(STRATEGY_NAME)
    snap = compute_snapshot(df)
    if snap.sma_50 and snap.sma_200 and snap.sma_50 > snap.sma_200:
        if snap.rsi is None or snap.rsi < float(cfg.get("rsi_max", 70.0)):
            return BuySignalEvent(
                ticker=context.ticker, user_id=context.user_id,
                source=STRATEGY_NAME, asset_class=context.asset_class,
            )
    return None
```

Sell strategies return a `SellSignalEvent`; set `quantity_pct` for a partial exit
(omit or `None` for a full exit).

## Indicators & regime

Import pure helpers directly:

```python
from src.modules.price.indicators import rsi, macd, atr, bollinger, compute_snapshot
from src.modules.price import regime
regime.detect(benchmark_df)  # "bull" | "bear" | "neutral"
```

## Activation

Each user has an active buy and sell strategy (config keys
`strategy.active_buy_strategy` / `strategy.active_sell_strategy`). Set them via the
Strategies page or `PATCH /api/v1/strategies/{name}/activate?direction=buy`.

## Distribution via git

User strategies can be committed to a strategy repo and synced by `modules/com/git`;
the commit hash becomes the strategy version.
```
