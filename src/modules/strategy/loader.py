"""Discover and load single-file strategies from ``strategies/buy`` and ``strategies/sell``.

Each strategy file must export ``STRATEGY_NAME``, ``STRATEGY_VERSION``, ``CONFIG_SCHEMA``
and an ``async def run(context) -> StrategyDecision``. Optional: ``STRATEGY_DESCRIPTION``,
``FEATURES`` (a list of UI feature tags the strategy uses, e.g. ``["signals"]`` — see
pages/StrategyDetail.tsx for how these drive the per-strategy sidebar page).
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from .context import StrategyContext, StrategyDecision

RunFn = Callable[[StrategyContext], Awaitable[StrategyDecision]]

_DIRECTIONS = ("buy", "sell")


class StrategyLoadError(Exception):
    pass


class DuplicateStrategyNameError(Exception):
    """Two or more strategy files declare the same STRATEGY_NAME — raised instead of
    silently letting one shadow the other (whichever a dict comprehension keeps last),
    which could otherwise replace a buy strategy with a same-named sell strategy
    (or vice versa) with no error anywhere (bugs.md finding 21)."""

    def __init__(self, name: str, paths: list[str]) -> None:
        self.name = name
        self.paths = paths
        super().__init__(
            f"duplicate STRATEGY_NAME '{name}' declared by multiple files: {', '.join(paths)}"
        )


@dataclass(slots=True)
class LoadedStrategy:
    name: str
    version: str
    direction: str
    file_path: str
    is_builtin: bool
    description: str | None
    features: list[str]
    config_schema: dict[str, dict[str, Any]]
    run: RunFn
    module: ModuleType
    external_sources: list[str]
    # Whether a *buy* strategy is evaluated over the shared price watchlist (the
    # default, True) or discovers its own candidate tickers instead (e.g.
    # strategies/buy/signal_follow.py sets USES_WATCHLIST = False to discover
    # candidates from its EXTERNAL_SOURCES directly — see
    # TradingRuntime.run_strategies / SignalSourceRegistry.discover in
    # src/api/runtime.py, src/modules/signal/sources.py). Meaningless for a sell
    # strategy, which always runs over open positions regardless.
    uses_watchlist: bool = True


def _require(module: ModuleType, attr: str, path: Path) -> Any:
    if not hasattr(module, attr):
        raise StrategyLoadError(f"{path} is missing required '{attr}'")
    return getattr(module, attr)


def load_strategy_file(path: Path, direction: str, builtin_root: str | Path | None = None) -> LoadedStrategy:
    module_name = f"lucid_strategy_{direction}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise StrategyLoadError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # Must be registered in sys.modules *before* exec_module: a strategy file using
    # @dataclass (or anything relying on typing.get_type_hints/postponed annotation
    # evaluation) has its field types resolved via
    # sys.modules.get(cls.__module__).__dict__ during class creation — if the module
    # isn't in sys.modules yet, that lookup returns None and raises
    # "AttributeError: 'NoneType' object has no attribute '__dict__'".
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    run = _require(module, "run", path)
    if not callable(run):
        raise StrategyLoadError(f"{path} 'run' is not callable")

    return LoadedStrategy(
        name=str(_require(module, "STRATEGY_NAME", path)),
        version=str(_require(module, "STRATEGY_VERSION", path)),
        direction=direction,
        file_path=f"strategies/{direction}/{path.name}",
        is_builtin=_is_builtin_file(path, direction, builtin_root),
        description=getattr(module, "STRATEGY_DESCRIPTION", None),
        features=list(getattr(module, "FEATURES", [])),
        config_schema=dict(_require(module, "CONFIG_SCHEMA", path)),
        run=run,
        module=module,
        # Third-party signal sources (see src/modules/signal/sources.py) this
        # strategy wants checked before each run() — e.g. EXTERNAL_SOURCES =
        # ["zacks", "tradingview"]. Optional; omitting it (the common case) means no
        # external network call is made on this strategy's behalf.
        external_sources=list(getattr(module, "EXTERNAL_SOURCES", [])),
        uses_watchlist=bool(getattr(module, "USES_WATCHLIST", True)),
    )


def _is_builtin_file(path: Path, direction: str, builtin_root: str | Path | None) -> bool:
    """"Native" vs "custom" is derived from actual file origin, not a self-declared
    flag in the strategy file (which a git-synced file could set just as easily as a
    real built-in) — a file only counts as native if it's byte-identical to the one
    shipped in ``BUILTIN_STRATEGIES_ROOT``. Anything git-sync deployed into
    ``STRATEGIES_ROOT`` — including an override that reuses a built-in's filename — is
    "custom", since ``deploy_strategies`` always overwrites on conflict.
    """
    if builtin_root is None:
        return False
    candidate = Path(builtin_root) / direction / path.name
    if not candidate.is_file():
        return False
    if candidate.resolve() == path.resolve():
        return True
    try:
        return candidate.read_bytes() == path.read_bytes()
    except OSError:
        return False


def discover_strategies(
    strategies_root: str | Path, builtin_root: str | Path | None = None
) -> list[LoadedStrategy]:
    # Defaults to strategies_root itself when no separate built-in source is given
    # (e.g. local dev/tests with no separate baked-in image layer) — every discovered
    # file then trivially compares equal to itself and counts as native. In
    # production these differ (see AppContext: STRATEGIES_ROOT vs
    # BUILTIN_STRATEGIES_ROOT), making the comparison meaningful.
    builtin_root = strategies_root if builtin_root is None else builtin_root
    root = Path(strategies_root)
    loaded: list[LoadedStrategy] = []
    for direction in _DIRECTIONS:
        directory = root / direction
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            loaded.append(load_strategy_file(path, direction, builtin_root))

    by_name: dict[str, list[str]] = {}
    for strategy in loaded:
        by_name.setdefault(strategy.name, []).append(strategy.file_path)
    duplicate = next(((name, paths) for name, paths in by_name.items() if len(paths) > 1), None)
    if duplicate is not None:
        raise DuplicateStrategyNameError(*duplicate)

    return loaded


def seed_missing_strategies(source_root: str | Path, target_root: str | Path) -> list[str]:
    """Copy built-in strategy files from ``source_root`` into ``target_root`` for any
    file that doesn't already exist there.

    Used at startup when ``STRATEGIES_ROOT`` is a fresh, writable, initially-empty
    bind mount (required so the git-synced deploy target isn't the read-only image
    layer) — without this, a brand-new mount would hide the built-in strategies baked
    into the image. Never overwrites an existing file, so a git-synced file with the
    same name always wins.
    """
    source = Path(source_root)
    target = Path(target_root)
    if source.resolve() == target.resolve():
        return []
    seeded: list[str] = []
    for direction in _DIRECTIONS:
        src_dir = source / direction
        if not src_dir.is_dir():
            continue
        dst_dir = target / direction
        dst_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(src_dir.glob("*.py")):
            dst_path = dst_dir / path.name
            if dst_path.exists():
                continue
            shutil.copy2(path, dst_path)
            seeded.append(f"{direction}/{path.name}")
    return seeded
