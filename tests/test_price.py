"""M7: indicators, regime detection, Parquet storage, and the pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.db.repositories.price import PriceWatchlistRepository, WatchlistAssetClassConflictError
from src.modules.price import indicators, regime, storage
from src.modules.price.pipeline import PricePipeline
from src.scripts.migrate_legacy_prices import migrate


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


def test_latest_price_prefers_newer_intraday_over_stale_daily(tmp_path) -> None:
    """Regression test for bugs.md finding 3: a stop/tier check or execution quote
    must use the freshest stored bar across intervals, not always the daily one."""
    idx_daily = pd.date_range("2023-01-01", periods=3, freq="D")
    daily = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0],
            "high": [100.0, 100.0, 100.0],
            "low": [100.0, 100.0, 100.0],
            "close": [100.0, 100.0, 100.0],
            "volume": [1000.0, 1000.0, 1000.0],
        },
        index=idx_daily,
    )
    storage.write_bars(tmp_path, "AAPL", "1d", daily)
    assert storage.latest_price(tmp_path, "AAPL") == 100.0

    idx_hourly = pd.date_range(idx_daily[-1] + pd.Timedelta(hours=1), periods=2, freq="h")
    hourly = pd.DataFrame(
        {
            "open": [80.0, 75.0],
            "high": [80.0, 75.0],
            "low": [80.0, 75.0],
            "close": [80.0, 75.0],
            "volume": [500.0, 500.0],
        },
        index=idx_hourly,
    )
    storage.write_bars(tmp_path, "AAPL", "1h", hourly)
    assert storage.latest_price(tmp_path, "AAPL") == 75.0


def test_latest_price_missing_ticker_returns_none(tmp_path) -> None:
    assert storage.latest_price(tmp_path, "NOPE") is None


async def test_price_watchlist_repository_crud(session: AsyncSession) -> None:
    repo = PriceWatchlistRepository(session)

    assert await repo.list_all() == []

    row = await repo.upsert("amzn", asset_class="equity")
    assert row.ticker == "AMZN"  # normalized to upper case
    assert row.enabled is True
    assert row.poll_interval == "1h"  # default
    assert row.region == "us"  # default
    assert [r.ticker for r in await repo.list_enabled()] == ["AMZN"]

    # upsert again with the SAME asset_class updates the existing row (fields other
    # than asset_class) rather than creating a duplicate.
    updated = await repo.upsert(
        "amzn", asset_class="equity", enabled=False, poll_interval="1m", region="eu"
    )
    assert updated.id == row.id
    assert updated.asset_class == "equity"
    assert updated.poll_interval == "1m"
    assert updated.region == "eu"
    assert await repo.list_enabled() == []

    # A conflicting asset_class is rejected, not silently applied (bugs.md finding 18).
    with pytest.raises(WatchlistAssetClassConflictError):
        await repo.upsert("amzn", asset_class="crypto")
    unchanged = await repo.get_by_ticker("AMZN")
    assert unchanged is not None and unchanged.asset_class == "equity"

    toggled = await repo.set_enabled("AMZN", True)
    assert toggled is not None
    assert toggled.enabled is True

    interval_updated = await repo.set_poll_interval("AMZN", "1h")
    assert interval_updated is not None
    assert interval_updated.poll_interval == "1h"
    assert await repo.set_poll_interval("NOPE", "1h") is None
    assert await repo.set_enabled("NOPE", True) is None

    region_updated = await repo.set_region("AMZN", "em")
    assert region_updated is not None
    assert region_updated.region == "em"
    assert await repo.set_region("NOPE", "us") is None

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

    async def on_fetched(ticker: str, interval: str, rows: int, duration: float) -> None:
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


async def test_pipeline_run_daily_calls_on_error_for_failed_ticker(tmp_path) -> None:
    df = _uptrend_df(20)

    async def fetcher(ticker: str, *, period: str, interval: str) -> pd.DataFrame:
        if ticker == "BAD":
            raise RuntimeError("provider down")
        return df

    async def watchlist() -> list[str]:
        return ["AAPL", "BAD"]

    errors: list[tuple[str, str, str]] = []

    async def on_error(ticker: str, interval: str, message: str, duration: float) -> None:
        errors.append((ticker, interval, message))

    pipeline = PricePipeline(
        storage_path=str(tmp_path),
        fetcher=fetcher,
        watchlist_provider=watchlist,
        on_error=on_error,
    )
    results = await pipeline.run_daily()
    assert results == {"AAPL": 20, "BAD": 0}
    assert len(errors) == 1
    assert errors[0][0] == "BAD"
    assert "provider down" in errors[0][2]


def test_migrate_legacy_prices_normalizes_columns_and_case(tmp_path) -> None:
    legacy_dir = tmp_path / "ohlcv"
    legacy_dir.mkdir()
    df = _uptrend_df(5)
    # Legacy layout: capitalized columns (yfinance-style), ticker filename lowercase.
    legacy_df = df.rename(columns={c: c.capitalize() for c in df.columns})
    legacy_df.to_parquet(legacy_dir / "amzn.parquet")

    storage_path = tmp_path / "prices"
    results = migrate(str(legacy_dir), str(storage_path), "1d")

    assert results == {"AMZN": 5}
    migrated = storage.read_bars(storage_path, "AMZN", "1d")
    assert migrated is not None
    assert list(migrated.columns) == ["open", "high", "low", "close", "volume"]
    assert len(migrated) == 5


def test_migrate_legacy_prices_skips_bad_file_without_raising(tmp_path, capsys) -> None:
    legacy_dir = tmp_path / "ohlcv"
    legacy_dir.mkdir()
    pd.DataFrame({"nonsense": [1, 2, 3]}).to_parquet(legacy_dir / "bad.parquet")

    results = migrate(str(legacy_dir), str(tmp_path / "prices"), "1d")

    assert results == {}
    assert "skip bad.parquet" in capsys.readouterr().out


def test_migrate_legacy_prices_merges_with_existing_new_layout_bars(tmp_path) -> None:
    legacy_dir = tmp_path / "ohlcv"
    legacy_dir.mkdir()
    storage_path = tmp_path / "prices"

    older = _uptrend_df(5)
    older.to_parquet(legacy_dir / "AMZN.parquet")
    newer = _uptrend_df(10).iloc[-3:]  # bars already fetched by the current pipeline
    storage.write_bars(storage_path, "AMZN", "1d", newer)

    migrate(str(legacy_dir), str(storage_path), "1d")

    merged = storage.read_bars(storage_path, "AMZN", "1d")
    assert len(merged) == 8  # 5 legacy + 3 already-current, deduped by timestamp
