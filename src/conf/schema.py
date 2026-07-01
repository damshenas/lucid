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


class TrailingStopConfig(BaseModel):
    enabled: bool = True
    atr_multiplier: float = 3.0
    profit_take_levels: list[float] = Field(default_factory=lambda: [20.0, 50.0])


class StrategyConfig(BaseModel):
    active_buy_strategy: str | None = None
    active_sell_strategy: str | None = "trailing_stop"
    trailing_stop: TrailingStopConfig = Field(default_factory=TrailingStopConfig)


class RiskConfig(BaseModel):
    enabled: bool = False
    max_single_trade_usd: float = 1000.0
    max_daily_buy_usd: float = 5000.0
    max_open_positions: int = 20
    max_position_pct: float = 15.0


class ScheduleConfig(BaseModel):
    task_timeout_seconds: int = 300
    poll_positions_seconds: int = 300
    daily_price_hour: int = 22
    intraday_price_minutes: int = 15
    strategy_scan_hour: int = 3
    git_sync_minutes: int = 0  # 0 disables scheduled git sync


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
    risk: RiskConfig = Field(default_factory=RiskConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    price: PriceConfig = Field(default_factory=PriceConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    logger: LoggerConfig = Field(default_factory=LoggerConfig)
