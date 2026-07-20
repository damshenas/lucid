"""External signal-source connectors, normalized behind one interface.

Wraps the HTTP connectors in ``src.modules.com`` (finviz/tradingview/zacks/barchart) —
each is a thin, provider-specific client returning that provider's own shape (see
their docstrings); this module is what turns "what does Zacks think about AMZN?" into
one common ``ExternalSignal`` strategies (via ``StrategyContext.external_signals``,
see ``src/api/runtime.py``) and the manual check endpoint
(``POST /api/v1/signals/sources/check``) can consume without caring which provider
answered.

A source only ever participates once its credentials are configured via
``/api/v1/credentials`` — ``<source>_base_url`` (required) and, optionally,
``<source>_api_key`` — exactly like every other platform credential (see
``src.modules.encryption.credentials``). With nothing configured, ``fetch`` returns a
"not configured" ``ExternalSignal`` per requested source rather than raising, so a
strategy (or the check endpoint) never has to special-case a missing integration.

Nothing here is called automatically for every strategy — only strategies that
declare interest via an optional module-level ``EXTERNAL_SOURCES: list[str]`` (mirrors
``FEATURES``, see ``src/modules/strategy/loader.py``) trigger a fetch, so a strategy
that doesn't use external data never pays the network cost.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.modules.com.barchart import BarchartConnector
from src.modules.com.finviz import FinvizConnector
from src.modules.com.tradingview import TradingViewConnector
from src.modules.com.zacks import ZacksConnector
from src.modules.encryption import CredentialNotConfiguredError
from src.modules.logger import get_logger

if TYPE_CHECKING:
    from src.modules.encryption import CredentialManager

_logger = get_logger("signal.sources")


@dataclass(slots=True)
class ExternalSignal:
    """One data provider's opinion on one ticker, normalized to buy/sell/hold.

    ``direction`` is ``None`` when the provider gave no usable rating, the source
    isn't configured, or the request failed — check ``error`` to tell "no opinion"
    apart from "couldn't ask".
    """

    source: str
    ticker: str
    direction: str | None  # "buy" | "sell" | "hold" | None
    raw: dict[str, Any] | None = None
    error: str | None = None


def _direction_from_rating(value: Any) -> str | None:
    """Best-effort buy/sell/hold parse for a provider's free-form rating text or a
    numeric score (positive/negative, e.g. TradingView's -1..+1 ``Recommend.All``)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 0.1:
            return "buy"
        if value < -0.1:
            return "sell"
        return "hold"
    label = str(value).strip().lower()
    if "buy" in label:
        return "buy"
    if "sell" in label:
        return "sell"
    if "hold" in label or "neutral" in label:
        return "hold"
    return None


def _zacks_direction(raw: dict[str, Any]) -> str | None:
    # Zacks Rank: 1=Strong Buy, 2=Buy, 3=Hold, 4=Sell, 5=Strong Sell.
    try:
        rank = int(raw.get("rank"))
    except (TypeError, ValueError):
        return None
    if rank in (1, 2):
        return "buy"
    if rank in (4, 5):
        return "sell"
    if rank == 3:
        return "hold"
    return None


DirectionFn = Callable[[dict[str, Any]], "str | None"]


@dataclass(slots=True)
class _Source:
    connector_cls: type
    fetch_method: str
    to_direction: DirectionFn
    # Bulk "every currently-rated ticker" method name on the same connector class —
    # used by SignalSourceRegistry.discover() for a strategy that doesn't rely on a
    # predefined ticker list (e.g. strategies/buy/signal_follow.py). Returns a list of
    # raw dicts shaped exactly like fetch_method's single-ticker result (each
    # including its own "ticker" key), so `to_direction` is reused unchanged.
    discover_method: str


_SOURCES: dict[str, _Source] = {
    "zacks": _Source(ZacksConnector, "fetch_rank", _zacks_direction, "fetch_ranks"),
    "tradingview": _Source(
        TradingViewConnector,
        "fetch_technicals",
        lambda r: _direction_from_rating(r.get("recommendation")),
        "fetch_all_technicals",
    ),
    "barchart": _Source(
        BarchartConnector,
        "fetch_opinion",
        lambda r: _direction_from_rating(r.get("opinion")),
        "fetch_all_opinions",
    ),
    "finviz": _Source(
        FinvizConnector,
        "fetch_metrics",
        lambda r: _direction_from_rating((r.get("metrics") or {}).get("recommendation")),
        "fetch_screener",
    ),
}

SOURCE_NAMES: tuple[str, ...] = tuple(_SOURCES.keys())


class SignalSourceRegistry:
    """Resolves per-source credentials and calls the requested connectors for one
    ticker. ``user_id=None`` resolves system-default credentials only (matches
    ``CredentialManager``'s cascade)."""

    def __init__(self, credentials: CredentialManager, *, user_id: int | None = None) -> None:
        self._credentials = credentials
        self._user_id = user_id

    async def fetch(self, ticker: str, sources: list[str] | None = None) -> list[ExternalSignal]:
        names = [n for n in (sources or SOURCE_NAMES) if n in _SOURCES]
        return [await self._fetch_one(name, ticker) for name in names]

    async def discover(self, sources: list[str] | None = None) -> list[ExternalSignal]:
        """Every currently-rated ticker from each requested (default: all configured)
        source, flattened into one list — the discovery counterpart to ``fetch()``,
        for a strategy that doesn't rely on a predefined ticker list (no
        per-ticker credential/connection failure here ever raises: an unconfigured
        or failing source simply contributes nothing, same philosophy as
        ``_fetch_one``'s ``error=`` handling)."""
        names = [n for n in (sources or SOURCE_NAMES) if n in _SOURCES]
        results: list[ExternalSignal] = []
        for name in names:
            results.extend(await self._discover_one(name))
        return results

    async def _discover_one(self, name: str) -> list[ExternalSignal]:
        source = _SOURCES[name]
        try:
            base_url = await self._credentials.get_for_user(f"{name}_base_url", self._user_id)
        except CredentialNotConfiguredError:
            return []

        api_key: str | None = None
        try:
            api_key = await self._credentials.get_for_user(f"{name}_api_key", self._user_id)
        except CredentialNotConfiguredError:
            pass  # optional for every current source

        connector = source.connector_cls(base_url, api_key=api_key)
        try:
            raw_items = await getattr(connector, source.discover_method)()
            return [
                ExternalSignal(
                    source=name, ticker=item["ticker"], direction=source.to_direction(item), raw=item
                )
                for item in raw_items
            ]
        except Exception as exc:  # noqa: BLE001 - one bad source must not break the rest
            _logger.warning("signal source %s discovery failed: %s", name, exc)
            return []
        finally:
            await connector.aclose()

    async def _fetch_one(self, name: str, ticker: str) -> ExternalSignal:
        source = _SOURCES[name]
        try:
            base_url = await self._credentials.get_for_user(f"{name}_base_url", self._user_id)
        except CredentialNotConfiguredError:
            return ExternalSignal(source=name, ticker=ticker, direction=None, error="not configured")

        api_key: str | None = None
        try:
            api_key = await self._credentials.get_for_user(f"{name}_api_key", self._user_id)
        except CredentialNotConfiguredError:
            pass  # optional for every current source

        connector = source.connector_cls(base_url, api_key=api_key)
        try:
            raw = await getattr(connector, source.fetch_method)(ticker)
            return ExternalSignal(source=name, ticker=ticker, direction=source.to_direction(raw), raw=raw)
        except Exception as exc:  # noqa: BLE001 - one bad source must not break the rest
            _logger.warning("signal source %s failed for %s: %s", name, ticker, exc)
            return ExternalSignal(source=name, ticker=ticker, direction=None, error=str(exc))
        finally:
            await connector.aclose()


__all__ = ["SOURCE_NAMES", "ExternalSignal", "SignalSourceRegistry"]
