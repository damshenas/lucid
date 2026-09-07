"""Parquet storage for OHLCV bars at ``<storage_path>/<interval>/<ticker>.parquet``."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_COLUMNS = ["open", "high", "low", "close", "volume"]


def bars_path(storage_path: str | Path, ticker: str, interval: str) -> Path:
    return Path(storage_path) / interval / f"{ticker.upper()}.parquet"


def write_bars(storage_path: str | Path, ticker: str, interval: str, df: pd.DataFrame) -> Path:
    path = bars_path(storage_path, ticker, interval)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return path


def read_bars(storage_path: str | Path, ticker: str, interval: str) -> pd.DataFrame | None:
    path = bars_path(storage_path, ticker, interval)
    if not path.exists():
        return None
    return pd.read_parquet(path)


def append_bars(storage_path: str | Path, ticker: str, interval: str, df: pd.DataFrame) -> Path:
    """Merge new bars with existing, dedup by index, sort, and persist."""
    existing = read_bars(storage_path, ticker, interval)
    if existing is not None and not existing.empty:
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = df.sort_index()
    return write_bars(storage_path, ticker, interval, combined)


def list_tickers(storage_path: str | Path, interval: str = "1d") -> list[str]:
    """Tickers that already have stored bars for ``interval`` — used to power the
    Prices page's ticker autocomplete (see GET /api/v1/prices in api/v1/prices.py)."""
    directory = Path(storage_path) / interval
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.parquet"))


def list_intervals(storage_path: str | Path) -> list[str]:
    """Every interval subdirectory that has ever been written to (e.g. "1d", "1h",
    "1m") — used by the admin price-coverage report (GET
    /api/v1/admin/reports/price-coverage) to discover what to scan without a fixed,
    hardcoded interval list."""
    root = Path(storage_path)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def latest_price(
    storage_path: str | Path, ticker: str, intervals: tuple[str, ...] = ("1m", "1h", "1d")
) -> float | None:
    """Most recent stored close across whichever of ``intervals`` has bars for this
    ticker — newest timestamp wins, so a stop-loss/tier check or an order's sizing
    quote uses fresh intraday data when it exists instead of always falling back to a
    stale daily close (bugs.md finding 3). ``None`` if no bars exist in any interval."""
    best_ts = None
    best_close: float | None = None
    for interval in intervals:
        df = read_bars(storage_path, ticker, interval)
        if df is None or df.empty:
            continue
        ts = df.index.max()
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best_close = float(df["close"].iloc[-1])
    return best_close
