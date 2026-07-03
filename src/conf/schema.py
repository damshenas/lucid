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
    strategy_scan_hour: int = 3


class GitSyncConfig(BaseModel):
    """System-level (admin-only) config for syncing algorithm files from a git repo.

    ``repo_url`` is cloned/pulled into the ``EXT_STRATEGIES`` staging directory (a
    mounted volume), then discovered ``buy``/``sell`` strategy files are copied into
    ``STRATEGIES_ROOT`` — the app never runs code directly out of the staging mount.
    """

    enabled: bool = False
    repo_url: str | None = None
    branch: str = "main"
    interval_minutes: int = 0  # 0 disables the scheduled sync (startup sync still runs)


class PriceConfig(BaseModel):
    storage_path: str = "/data/prices"
    backfill_days: int = 365
    intraday_interval: str = "15m"
    benchmark_ticker: str = "SPY"


class BrokerConfig(BaseModel):
    broker_name: str = "trading212"
    paper_mode: bool = True


class LoggerConfig(BaseModel):
    level: str = "INFO"
    file_path: str | None = "/data/lucid.log"


class LucidConfig(BaseModel):
    """Root config model — mirrors the sections in ``default.yml``."""

    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    git_sync: GitSyncConfig = Field(default_factory=GitSyncConfig)
    price: PriceConfig = Field(default_factory=PriceConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    logger: LoggerConfig = Field(default_factory=LoggerConfig)
