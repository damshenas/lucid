"""One-off CLI: migrate a legacy price parquet layout into the current
``<storage_path>/<interval>/<TICKER>.parquet`` scheme (see ``src.modules.price.storage``).

Symptom this fixes: ``GET /api/v1/prices/{ticker}`` returns ``404: no bars for X
[1d]`` even though a parquet file clearly exists on disk for that ticker — because
it's sitting under an old, descriptively-named directory (e.g. ``ohlcv/`` for daily
bars, ``ohlcv_1m/`` for 1-minute bars) from a previous pipeline, instead of the
interval-named directory (``1d/``, ``1m/``, ...) this app's ``storage.py`` reads from.
Nothing in this codebase ever wrote to an ``ohlcv``-style directory — if you have one,
it predates this pipeline (or came from a different app) and needs a one-time copy.

Not run automatically by anything (no startup hook, no scheduled job) — a human runs
it once, on purpose, against a specific legacy directory:

    python -m src.scripts.migrate_legacy_prices /data/prices/ohlcv /data/prices 1d
    python -m src.scripts.migrate_legacy_prices /data/prices/ohlcv_1m /data/prices 1m

Column names are matched case-insensitively (``Open``/``OPEN``/``open`` all map to
``open``, etc., same normalization ``com.yahoofinance`` applies to fresh fetches) and
the index is coerced to a ``DatetimeIndex`` if it isn't already one. A file whose
columns don't cover open/high/low/close/volume is skipped (reported, not fatal) rather
than guessed at. Merging uses ``storage.append_bars`` — dedup by timestamp, sorted,
never simply overwrites — so re-running is always safe.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from src.modules.price import storage

_REQUIRED = ("open", "high", "low", "close", "volume")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    df = df.rename(columns={c: str(c).strip().lower() for c in df.columns})
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing required column(s) {missing} — got {list(df.columns)}")
    df = df[list(_REQUIRED)]
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df.sort_index()


def migrate(legacy_dir: str, storage_path: str, interval: str) -> dict[str, int]:
    """Copy every ``*.parquet`` file under ``legacy_dir`` into
    ``<storage_path>/<interval>/<TICKER>.parquet``. Returns ``{ticker: rows_merged}``
    for files that succeeded; failed files are printed and omitted."""
    src_dir = Path(legacy_dir)
    if not src_dir.is_dir():
        raise SystemExit(f"not a directory: {src_dir}")

    results: dict[str, int] = {}
    files = sorted(src_dir.glob("*.parquet"))
    if not files:
        print(f"no .parquet files found under {src_dir}")
        return results

    for path in files:
        ticker = path.stem.upper()
        try:
            df = _normalize(pd.read_parquet(path))
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
            print(f"skip {path.name}: {exc}")
            continue
        storage.append_bars(storage_path, ticker, interval, df)
        results[ticker] = len(df)
        print(f"migrated {ticker}: {len(df)} row(s) -> {storage.bars_path(storage_path, ticker, interval)}")

    return results


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: python -m src.scripts.migrate_legacy_prices <legacy_dir> <storage_path> <interval>"
        )
    migrate(sys.argv[1], sys.argv[2], sys.argv[3])
