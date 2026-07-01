"""Yahoo Finance data connector (yfinance wrapper).

Returns a normalized OHLCV frame with lowercase columns and a DatetimeIndex. The
blocking yfinance call runs in a worker thread.
"""

from __future__ import annotations

import asyncio

import pandas as pd

REQUIRED_CONFIG: list[str] = []
OPTIONAL_CONFIG = {"auto_adjust": True}

_RENAME = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    df = df.rename(columns=_RENAME)
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep]
    df.index = pd.to_datetime(df.index)
    return df


async def fetch_ohlcv(
    ticker: str, *, period: str = "1y", interval: str = "1d", auto_adjust: bool = True
) -> pd.DataFrame:
    import yfinance as yf

    def _download() -> pd.DataFrame:
        return yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=auto_adjust,
            progress=False,
        )

    raw = await asyncio.to_thread(_download)
    return _normalize(raw)


__all__ = ["OPTIONAL_CONFIG", "REQUIRED_CONFIG", "fetch_ohlcv"]
