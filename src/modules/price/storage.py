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
