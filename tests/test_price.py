"""M7: indicators, regime detection, Parquet storage, and the pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.db.repositories.price import PriceWatchlistRepository
from src.modules.price import indicators, regime, storage
from src.modules.price.pipeline import PricePipeline


def _uptrend_df(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100.0, 200.0, n), index=idx)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": pd.Series(np.full(n, 1000.0), index=idx),
        }
    )


def test_rsi_bounds() -> None:
    df = _uptrend_df()
    value = indicators._last(indicators.rsi(df["close"]))
    assert value is not None
    assert 0.0 <= value <= 100.0
    assert value > 50.0  # steady uptrend


def test_snapshot_fields() -> None:
    snap = indicators.compute_snapshot(_uptrend_df())
    assert snap.sma_50 is not None
    assert snap.sma_200 is not None
    assert snap.sma_50 > snap.sma_200  # uptrend


def test_regime_bull_and_neutral() -> None:
    assert regime.detect(_uptrend_df()) == regime.BULL
    assert regime.detect(_uptrend_df(50)) == regime.NEUTRAL  # not enough history


def test_storage_round_trip(tmp_path) -> None:
    df = _uptrend_df(10)
    storage.write_bars(tmp_path, "AAPL", "1d", df)
    loaded = storage.read_bars(tmp_path, "AAPL", "1d")
    assert loaded is not None
    # Parquet does not preserve DatetimeIndex freq metadata; values still match.
    pd.testing.assert_frame_equal(loaded, df, check_freq=False)


def test_storage_append_dedup(tmp_path) -> None:
    df = _uptrend_df(10)
    storage.append_bars(tmp_path, "AAPL", "1d", df)
    storage.append_bars(tmp_path, "AAPL", "1d", df.iloc[-3:])  # overlapping
    loaded = storage.read_bars(tmp_path, "AAPL", "1d")
    assert len(loaded) == 10  # no duplicates


def test_storage_list_tickers(tmp_path) -> None:
    assert storage.list_tickers(tmp_path) == []
    storage.write_bars(tmp_path, "AAPL", "1d", _uptrend_df(5))
    storage.write_bars(tmp_path, "MSFT", "1d", _uptrend_df(5))
    assert storage.list_tickers(tmp_path) == ["AAPL", "MSFT"]
    assert storage.list_tickers(tmp_path, "15m") == []  # different interval, no files


async def test_price_watchlist_repository_crud(session: AsyncSession) -> None:
    repo = PriceWatchlistRepository(session)

    assert await repo.list_all() == []

    row = await repo.upsert("amzn", asset_class="equity")
    assert row.ticker == "AMZN"  # normalized to upper case
    assert row.enabled is True
    assert [r.ticker for r in await repo.list_enabled()] == ["AMZN"]

    # upsert again updates the existing row rather than creating a duplicate
    updated = await repo.upsert("amzn", asset_class="crypto", enabled=False)
    assert updated.id == row.id
    assert updated.asset_class == "crypto"
    assert await repo.list_enabled() == []

    toggled = await repo.set_enabled("AMZN", True)
    assert toggled is not None
    assert toggled.enabled is True
    assert await repo.set_enabled("NOPE", True) is None

    assert await repo.delete_by_ticker("AMZN") is True
    assert await repo.delete_by_ticker("AMZN") is False
    assert await repo.list_all() == []


async def test_pipeline_run_daily(tmp_path) -> None:
    df = _uptrend_df(20)

    async def fetcher(ticker: str, *, period: str, interval: str) -> pd.DataFrame:
        return df

    async def watchlist() -> list[str]:
        return ["AAPL", "MSFT"]

    fetched: list[tuple[str, str, int]] = []

    async def on_fetched(ticker: str, interval: str, rows: int) -> None:
        fetched.append((ticker, interval, rows))

    pipeline = PricePipeline(
        storage_path=str(tmp_path),
        fetcher=fetcher,
        watchlist_provider=watchlist,
        on_fetched=on_fetched,
    )
    results = await pipeline.run_daily()
    assert results == {"AAPL": 20, "MSFT": 20}
    assert len(fetched) == 2
    assert storage.read_bars(tmp_path, "AAPL", "1d") is not None
