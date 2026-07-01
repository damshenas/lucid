"""Discover and load single-file strategies from ``strategies/buy`` and ``strategies/sell``.

Each strategy file must export ``STRATEGY_NAME``, ``STRATEGY_VERSION``, ``CONFIG_SCHEMA``
and an ``async def run(context)``. Optional: ``STRATEGY_DESCRIPTION``, ``STRATEGY_BUILTIN``.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from .context import StrategyContext

RunFn = Callable[[StrategyContext], Awaitable[Any]]

_DIRECTIONS = ("buy", "sell")


class StrategyLoadError(Exception):
    pass


@dataclass(slots=True)
class LoadedStrategy:
    name: str
    version: str
    direction: str
    file_path: str
    is_builtin: bool
    description: str | None
    config_schema: dict[str, dict[str, Any]]
    run: RunFn
    module: ModuleType


def _require(module: ModuleType, attr: str, path: Path) -> Any:
    if not hasattr(module, attr):
        raise StrategyLoadError(f"{path} is missing required '{attr}'")
    return getattr(module, attr)


def load_strategy_file(path: Path, direction: str) -> LoadedStrategy:
    module_name = f"lucid_strategy_{direction}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise StrategyLoadError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    run = _require(module, "run", path)
    if not callable(run):
        raise StrategyLoadError(f"{path} 'run' is not callable")

    return LoadedStrategy(
        name=str(_require(module, "STRATEGY_NAME", path)),
        version=str(_require(module, "STRATEGY_VERSION", path)),
        direction=direction,
        file_path=f"strategies/{direction}/{path.name}",
        is_builtin=bool(getattr(module, "STRATEGY_BUILTIN", False)),
        description=getattr(module, "STRATEGY_DESCRIPTION", None),
        config_schema=dict(_require(module, "CONFIG_SCHEMA", path)),
        run=run,
        module=module,
    )


def discover_strategies(strategies_root: str | Path) -> list[LoadedStrategy]:
    root = Path(strategies_root)
    loaded: list[LoadedStrategy] = []
    for direction in _DIRECTIONS:
        directory = root / direction
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            loaded.append(load_strategy_file(path, direction))
    return loaded
