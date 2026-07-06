# Strategy authoring guide (read this before writing a new strategy)

This is the reference for **any** buy or sell strategy added to this repo — including
one written by an LLM/agent asked to "add a new strategy". It's self-contained: you
should not need to read the rest of the codebase to get a strategy working, though
`docs/strategies.md` and `src/modules/strategy/context.py` are the source of truth if
anything here and the code ever disagree.

## 1. File location

One **flat, single `.py` file** per strategy:

- Buy strategy → `strategies/buy/<name>.py`
- Sell strategy → `strategies/sell/<name>.py`

No subdirectories, no shared imports between strategy files. A filename starting with
`_` is ignored (use that prefix for a private helper module you don't want treated as
a strategy). Files are (re)discovered at startup and via `POST
/api/v1/strategies/scan` — there's no periodic auto-scan, so a newly added file won't
be selectable until one of those two things happens.

## 2. Required module-level exports

```python
STRATEGY_NAME: str        # unique identifier, used everywhere (config keys, UI, DB)
STRATEGY_VERSION: str     # semver or a git hash — just needs to change when logic does
CONFIG_SCHEMA: dict       # {"key": {"type": "float"|"int"|"str"|"bool", "default": ..., "required": bool}}

async def run(context: StrategyContext) -> StrategyDecision
```

`CONFIG_SCHEMA` keys are automatically folded into the Settings UI under
`strategy.<STRATEGY_NAME>.<key>` — you don't register them anywhere else.

Optional module-level attributes:

```python
STRATEGY_DESCRIPTION: str        # shown in the UI
FEATURES: list[str]              # UI feature tags — only "signals" currently means
                                  # anything (shows this strategy's own Signals feed
                                  # on its detail page)
EXTERNAL_SOURCES: list[str]      # third-party ratings to fetch before every run() —
                                  # see "External signal sources" below
```

"Native" vs "custom" in the UI is derived automatically (byte-identical to the
built-in copy shipped in the image), not a flag you set.

## 3. The contract: `StrategyContext` → `StrategyDecision`

```python
@dataclass(slots=True)
class StrategyContext:
    ticker: str
    user_id: int
    asset_class: str                      # "equity" | "commodity" | "crypto" | "fx"
    config: dict[str, Any]
    price_data: pd.DataFrame | None        # OHLCV, lowercase columns, DatetimeIndex
    position: PositionView | None          # sell strategies only — quantity/avg_price
    external_signals: list[ExternalSignal]  # see EXTERNAL_SOURCES below; [] if unused

    def strategy_config(self, name: str) -> dict[str, Any]: ...   # your CONFIG_SCHEMA values
    def external_signal(self, source: str) -> ExternalSignal | None: ...
```

```python
@dataclass(slots=True)
class StrategyDecision:
    acted: bool
    reasoning: str                                   # ALWAYS required, even acted=False
    event: BuySignalEvent | SellSignalEvent | None = None  # required when acted=True
```

**Every branch of `run()` must return a `reasoning` string that explains that specific
outcome** — not just the acted-on case. This "why did/didn't it act" text is exactly
what the per-strategy Decisions log in the UI shows, and it's the only thing an
operator (or you, debugging later) has to go on. Don't return a generic message for
the non-acting path.

## 4. Minimal buy example

```python
from __future__ import annotations

from src.modules.bus import BuySignalEvent
from src.modules.price.indicators import compute_snapshot
from src.modules.strategy.context import StrategyContext, StrategyDecision

STRATEGY_NAME = "my_buy_strategy"
STRATEGY_VERSION = "1.0.0"
STRATEGY_DESCRIPTION = "One-line summary of the idea."
CONFIG_SCHEMA = {
    "rsi_max": {"type": "float", "default": 70.0, "required": False},
}


async def run(context: StrategyContext) -> StrategyDecision:
    df = context.price_data
    if df is None or len(df) < 200:
        have = 0 if df is None else len(df)
        return StrategyDecision(acted=False, reasoning=f"only {have} bars stored, need 200")

    cfg = context.strategy_config(STRATEGY_NAME)
    rsi_max = float(cfg.get("rsi_max", CONFIG_SCHEMA["rsi_max"]["default"]))

    snap = compute_snapshot(df)
    if snap.sma_50 is None or snap.sma_200 is None:
        return StrategyDecision(acted=False, reasoning="SMA50/SMA200 not available yet")

    if snap.sma_50 > snap.sma_200 and (snap.rsi is None or snap.rsi < rsi_max):
        reasoning = f"uptrend (SMA50 {snap.sma_50:.2f} > SMA200 {snap.sma_200:.2f}), RSI ok"
        return StrategyDecision(
            acted=True,
            reasoning=reasoning,
            event=BuySignalEvent(
                ticker=context.ticker,
                user_id=context.user_id,
                source=STRATEGY_NAME,
                asset_class=context.asset_class,
                confidence=0.6,
                reasoning=reasoning,
            ),
        )
    return StrategyDecision(acted=False, reasoning="no uptrend or RSI overbought")
```

See `strategies/buy/trend_follow.py` for the real built-in equivalent.

## 5. Minimal sell example

Sell strategies additionally receive `context.position` (never `None` when `run()` is
called — the runtime only invokes a sell strategy for tickers the user actually
holds). Return a `SellSignalEvent`; set `quantity_pct` for a partial exit, or omit it
(`None`) for a full exit.

```python
from src.modules.bus import SellSignalEvent
from src.modules.strategy.context import StrategyContext, StrategyDecision

STRATEGY_NAME = "my_sell_strategy"
STRATEGY_VERSION = "1.0.0"
CONFIG_SCHEMA = {"stop_pct": {"type": "float", "default": 10.0, "required": False}}


async def run(context: StrategyContext) -> StrategyDecision:
    position = context.position
    df = context.price_data
    if df is None or df.empty:
        return StrategyDecision(acted=False, reasoning="no stored price bars yet")

    cfg = context.strategy_config(STRATEGY_NAME)
    stop_pct = float(cfg.get("stop_pct", CONFIG_SCHEMA["stop_pct"]["default"]))
    price = float(df["close"].iloc[-1])
    stop_price = position.avg_price * (1 - stop_pct / 100.0)

    if price < stop_price:
        reasoning = f"price {price:.2f} broke stop ({stop_price:.2f})"
        return StrategyDecision(
            acted=True,
            reasoning=reasoning,
            event=SellSignalEvent(
                ticker=context.ticker, user_id=context.user_id,
                source=STRATEGY_NAME, asset_class=context.asset_class,
                reasoning=reasoning,
            ),
        )
    return StrategyDecision(acted=False, reasoning=f"holding: {price:.2f} above stop {stop_price:.2f}")
```

See `strategies/sell/trailing_stop.py` for the real built-in equivalent.

## 6. Indicators & regime helpers

Pure functions, no DB/network — import directly:

```python
from src.modules.price.indicators import rsi, macd, atr, bollinger, compute_snapshot
from src.modules.price import regime
regime.detect(benchmark_df)  # "bull" | "bear" | "neutral"
```

## 7. Which tickers actually get evaluated (read this if a strategy "does nothing")

Activating a strategy is not, by itself, enough to see it act — what ticker(s) it
gets called with depends on the strategy's direction, and the two directions are
deliberately asymmetric:

- **Sell strategies** run over every ticker the user currently holds an **open
  position** in (`PositionRepository.list_all_open` — see
  `TradingRuntime.run_strategies` in `src/api/runtime.py`). A position is itself the
  universe; there is nothing to configure. If you bought AMZN, your active sell
  strategy will be evaluated against AMZN every poll, whether or not AMZN is on the
  watchlist below.
- **Buy strategies** run over the shared **price watchlist**
  (`GET/POST/PATCH/DELETE /api/v1/prices/watchlist`, managed from the Prices page's
  Watchlist card). This is the one part a strategy genuinely cannot "handle itself":
  deciding what to *consider* buying requires some list of candidate tickers, and
  scanning the whole market on every poll isn't practical (rate limits, cost). The
  watchlist is that curated candidate list — add a ticker there for any buy strategy
  to ever have a chance to fire on it. An empty watchlist means no buy signal will
  ever be produced, regardless of which buy strategy is active.

Either way, a ticker also needs **stored price bars on disk** before any strategy
runs against it — see the price system section below.

## 8. Price data prerequisite

`context.price_data` comes from Parquet files at
`<price.storage_path>/<interval>/<TICKER>.parquet` (`src/modules/price/storage.py`).
If nothing has ever fetched a ticker, `price_data` is `None` and your strategy should
say so and return `acted=False` (see the examples above) rather than raising. Trigger
a first fetch via `POST /api/v1/prices/backfill` (or the Prices page's "Load" /
backfill action) — the daily/intraday scheduled jobs only keep already-known tickers
(watchlist ∪ open positions) up to date, they don't discover new ones.

## 9. External signal sources (optional)

If your strategy wants a third-party opinion (Finviz/TradingView/Zacks/Barchart — see
`src/modules/signal/sources.py`) in addition to your own price-based logic, declare
it:

```python
EXTERNAL_SOURCES = ["zacks", "tradingview"]
```

The runtime fetches those sources for you before calling `run()` and hands you the
normalized results:

```python
async def run(context: StrategyContext) -> StrategyDecision:
    zacks = context.external_signal("zacks")           # ExternalSignal | None
    if zacks is not None and zacks.direction == "buy":
        ...
```

`ExternalSignal` has `source`, `ticker`, `direction` (`"buy" | "sell" | "hold" | None`),
`raw` (the provider's own response shape), and `error` (set when the source failed or
isn't configured — treat that the same as "no opinion", never raise). A source only
participates once an admin/trader has configured its credentials via
`/api/v1/credentials` (`<source>_base_url`, optionally `<source>_api_key`) — check
what's currently usable with `GET /api/v1/signals/sources`, and test one ticker
on-demand with `POST /api/v1/signals/sources/check` (body: `{"ticker": "AAPL",
"sources": ["zacks"]}`) without waiting for a scheduled strategy run. Omitting
`EXTERNAL_SOURCES` (the default) means zero extra network calls on your strategy's
behalf.

## 10. Activation

Each user has one active buy strategy and one active sell strategy (config keys
`strategy.active_buy_strategy` / `strategy.active_sell_strategy`) — set via Settings >
Strategy in the UI or `PATCH /api/v1/strategies/{name}/activate?direction=buy|sell`.

## 11. Testing your strategy

Add a test alongside the existing ones in `tests/strategies/test_builtin_strategies.py`
— construct a `StrategyContext` directly with a synthetic `price_data` DataFrame and
assert on the returned `StrategyDecision`, the same pattern used there for
`trend_follow`/`trailing_stop`. Verify with `docker build -f docker/Dockerfile -t
lucid-test .` from the repo root (this runs the full test suite) — never `pytest`
directly on the host.

## 12. Distribution via git (optional)

A strategy file can be committed to a separate strategy repo and synced in via
`src/modules/com/git` (`POST /api/v1/admin/git-sync` or the automatic startup sync) —
the commit hash becomes the strategy's effective version, and a same-named file always
overrides a built-in.
