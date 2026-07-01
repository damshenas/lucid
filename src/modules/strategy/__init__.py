"""Strategy framework: context, single-file loader, and registry service."""

from __future__ import annotations

from .context import PositionView, StrategyContext
from .loader import LoadedStrategy, StrategyLoadError, discover_strategies, load_strategy_file
from .registry import StrategyRegistryService, build_extra_sections

__all__ = [
    "LoadedStrategy",
    "PositionView",
    "StrategyContext",
    "StrategyLoadError",
    "StrategyRegistryService",
    "build_extra_sections",
    "discover_strategies",
    "load_strategy_file",
]
