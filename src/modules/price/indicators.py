"""Technical indicators — pure functions over OHLCV data. No DB, no network.

Strategies import these directly. Inputs are pandas Series/DataFrames with lowercase
columns ``open, high, low, close, volume``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    line = ema_fast - ema_slow
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return line, signal_line, line - signal_line


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def bollinger(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid + num_std * std, mid, mid - num_std * std


def momentum(close: pd.Series, period: int = 10) -> pd.Series:
    return close / close.shift(period) - 1.0


def volume_zscore(volume: pd.Series, period: int = 20) -> pd.Series:
    mean = volume.rolling(period).mean()
    std = volume.rolling(period).std()
    return (volume - mean) / std


def _last(series: pd.Series) -> float | None:
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    return float(cleaned.iloc[-1])


@dataclass(slots=True)
class TechnicalSnapshot:
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    atr: float | None = None
    bb_upper: float | None = None
    bb_mid: float | None = None
    bb_lower: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_20: float | None = None
    momentum: float | None = None
    volume_z: float | None = None


def compute_snapshot(df: pd.DataFrame) -> TechnicalSnapshot:
    """Compute the latest value of each indicator from an OHLCV frame."""
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    macd_line, macd_sig, macd_hist = macd(close)
    bb_upper, bb_mid, bb_lower = bollinger(close)
    return TechnicalSnapshot(
        rsi=_last(rsi(close)),
        macd=_last(macd_line),
        macd_signal=_last(macd_sig),
        macd_hist=_last(macd_hist),
        atr=_last(atr(high, low, close)),
        bb_upper=_last(bb_upper),
        bb_mid=_last(bb_mid),
        bb_lower=_last(bb_lower),
        sma_50=_last(sma(close, 50)),
        sma_200=_last(sma(close, 200)),
        ema_20=_last(ema(close, 20)),
        momentum=_last(momentum(close)),
        volume_z=_last(volume_zscore(volume)),
    )
