"""Pydantic v2 models for all configuration sections.

Only non-sensitive settings live here. Secrets (API keys, tokens, passwords) are
never part of this schema — they come from the encrypted DB credential store.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AssetClass(str, Enum):
    equity = "equity"
    commodity = "commodity"
    crypto = "crypto"
    fx = "fx"


class QuantityMode(str, Enum):
    fixed_usd = "fixed_usd"
    pct_portfolio = "pct_portfolio"
    half_kelly = "half_kelly"


class LogLevel(str, Enum):
    debug = "DEBUG"
    info = "INFO"
    warning = "WARNING"
    error = "ERROR"
    critical = "CRITICAL"


class ExecutionConfig(BaseModel):
    quantity_mode: QuantityMode = QuantityMode.fixed_usd
    fixed_usd: float = 100.0
    pct_portfolio: float = 5.0
    dedup_window_seconds: int = 300


class StrategyConfig(BaseModel):
    active_buy_strategy: str | None = None
    active_sell_strategy: str | None = "trailing_stop"
    # Per-strategy tunables (e.g. trailing_stop's atr_multiplier) live entirely in
    # each strategy file's own CONFIG_SCHEMA — see strategies/{buy,sell}/*.py and
    # StrategyRegistryService.all_extra_sections — not here, to avoid two competing
    # sources of truth for the same "strategy.<name>.<field>" config keys.


class ScheduleConfig(BaseModel):
    task_timeout_seconds: int = 300
    poll_positions_seconds: int = 300
    daily_price_hour: int = 22
    intraday_price_minutes: int = 15
    # Gates intraday price-fetch jobs and strategy evaluation (run_strategies) by each
    # ticker's watchlist region (see PriceWatchlist.region,
    # src/modules/schedules/market_hours.py) — a closed-market ticker is skipped
    # until its region's session opens. Does not affect the daily ("1d") fetch.
    market_hours_enabled: bool = True
    # Strategy files are (re)scanned at startup and via the manual "Rescan" button
    # (POST /api/v1/strategies/scan) only — no periodic auto-scan.


class PriceConfig(BaseModel):
    storage_path: str = "/data/prices"
    backfill_days: int = 365
    # Intraday bar granularity is set per-ticker on the watchlist itself ("1m" or
    # "1h", default "1h" — see PriceWatchlist.poll_interval), not here.
    benchmark_ticker: str = "SPY"


class BrokerConfig(BaseModel):
    broker_name: str = "trading212"
    paper_mode: bool = True


class LoggerConfig(BaseModel):
    level: LogLevel = LogLevel.info
    file_path: str | None = "/data/lucid.log"


class LucidConfig(BaseModel):
    """Root config model — mirrors the sections in ``default.yml``."""

    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    price: PriceConfig = Field(default_factory=PriceConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    logger: LoggerConfig = Field(default_factory=LoggerConfig)
