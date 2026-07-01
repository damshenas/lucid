"""Async repositories, one per model, plus the generic ``BaseRepository``."""

from __future__ import annotations

from .base import BaseRepository
from .config import ConfigRepository
from .credential import CredentialRepository
from .daily_loss import DailyLossRepository
from .order import OrderRepository
from .position import PositionRepository
from .price import PriceFetchLogRepository, PriceWatchlistRepository
from .signal import SignalOutcomeRepository, SignalRepository
from .strategy import StrategyRepository
from .user import UserRepository

__all__ = [
    "BaseRepository",
    "ConfigRepository",
    "CredentialRepository",
    "DailyLossRepository",
    "OrderRepository",
    "PositionRepository",
    "PriceFetchLogRepository",
    "PriceWatchlistRepository",
    "SignalOutcomeRepository",
    "SignalRepository",
    "StrategyRepository",
    "UserRepository",
]
