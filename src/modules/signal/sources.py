"""External signal-source connectors, normalized behind one interface.

Wraps the HTTP connectors in ``src.modules.com`` — each is a thin, provider-specific
client returning that provider's own shape (see their docstrings); this module is
what turns "what does Finviz think about AMZN?" into one common ``ExternalSignal``
strategies (via ``StrategyContext.external_signals``, see ``src/api/runtime.py``) and
the manual check endpoint (``POST /api/v1/signals/sources/check``) can consume
without caring which provider answered.

Currently wired sources:

- **finviz** and **tradingview**: real, fixed public endpoints (a screener page, a
  scanner API), no credentials needed at all (see their connector docstrings).
- **finnhub** (Recommendation Trends — analyst consensus buckets) and **fmp_rating**/
  **fmp_grades** (Financial Modeling Prep's fundamentals rating snapshot and analyst
  grade consensus, respectively): free-tier public REST APIs that need only an API
  key (``finnhub_api_key`` / ``fmp_api_key`` — no configurable base URL, see
  ``requires_credentials``/``needs_base_url`` below).
- **zacks** and **barchart** exist only as ``DISABLED`` placeholders
  (``src.modules.com.zacks``/``.barchart``) since their real data requires a
  headless-browser anti-bot bypass this repo doesn't run — they are intentionally
  absent from ``_SOURCES``/``SOURCE_NAMES`` below, not merely "unconfigured".

Every source normalizes to the standard 5-level ``rating`` (see
``src.modules.signal.rating``: strong_buy/buy/neutral/sell/strong_sell) in addition to
the simpler buy/hold/sell ``direction`` existing strategy vote-counting already reads
(``signal_follow.min_buy_votes``) — ``direction`` is just ``rating`` collapsed via
``rating.direction_from_rating``.

A source that declares ``requires_credentials=True`` only participates once its
credentials are configured via ``/api/v1/credentials``. Most such sources need only
an ``<source>_api_key`` (``needs_base_url=False`` — a fixed public API, e.g. finnhub/
fmp); the mechanism still supports a future ``<source>_base_url``-configurable source
too. With nothing configured, ``fetch``/``discover`` return a "not configured" result
for it rather than raising, so a strategy (or the check endpoint) never has to
special-case a missing integration.

Nothing here is called automatically for every strategy — only strategies that
declare interest via an optional module-level ``EXTERNAL_SOURCES: list[str]`` (mirrors
``FEATURES``, see ``src/modules/strategy/loader.py``) trigger a fetch, so a strategy
that doesn't use external data never pays the network cost.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.modules.com.finnhub import FinnhubConnector
from src.modules.com.fmp import FMPConnector, rating_from_overall_score
from src.modules.com.finviz import FinvizConnector
from src.modules.com.tradingview import TradingViewConnector
from src.modules.encryption import CredentialNotConfiguredError
from src.modules.logger import get_logger
from src.modules.signal.rating import (
    direction_from_rating,
    rating_from_score,
    rating_from_text,
    rating_from_vote_counts,
)

if TYPE_CHECKING:
    from src.modules.encryption import CredentialManager

_logger = get_logger("signal.sources")


@dataclass(slots=True)
class ExternalSignal:
    """One data provider's opinion on one ticker, normalized to the standard
    5-level rating (plus a simpler buy/sell/hold ``direction`` for existing
    vote-counting strategies).

    ``rating``/``direction`` are ``None`` when the provider gave no usable
    rating, the source isn't configured, or the request failed — check
    ``error`` to tell "no opinion" apart from "couldn't ask".
    """

    source: str
    ticker: str
    direction: str | None  # "buy" | "sell" | "hold" | None
    rating: str | None = None  # "strong_buy" | "buy" | "neutral" | "sell" | "strong_sell" | None
    raw: dict[str, Any] | None = None
    error: str | None = None


def _rating_from_value(value: Any) -> str | None:
    """Best-effort 5-level rating from a provider's free-form rating text or a
    numeric score (e.g. TradingView's -1..+1 ``Recommend.All``)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return rating_from_score(value)
    return rating_from_text(str(value))


RatingFn = Callable[[dict[str, Any]], "str | None"]


@dataclass(slots=True)
class _Source:
    connector_cls: type
    fetch_method: str
    # Maps this connector's raw single-ticker result dict to the standard 5-level
    # rating ("strong_buy"/"buy"/"neutral"/"sell"/"strong_sell"); ``direction`` is
    # then derived from this via ``rating.direction_from_rating``.
    to_rating: RatingFn
    # Bulk "every currently-rated ticker" method name on the same connector class —
    # used by SignalSourceRegistry.discover() for a strategy that doesn't rely on a
    # predefined ticker list (e.g. strategies/buy/signal_follow.py). Returns a list of
    # raw dicts shaped exactly like fetch_method's single-ticker result (each
    # including its own "ticker" key), so `to_rating` is reused unchanged. ``None``
    # for a source with no bulk endpoint (e.g. finnhub/fmp on their free tiers) —
    # such a source is simply skipped by discover(), fetch()-only.
    discover_method: str | None = None
    # Whether this source needs any credentials at all before it can be used. False
    # for finviz/tradingview (fixed public endpoints, no auth). True for finnhub/fmp
    # (need an API key) — see needs_base_url/credential_prefix below.
    requires_credentials: bool = False
    # Whether this source needs a configurable <prefix>_base_url credential in
    # addition to <prefix>_api_key. False for finnhub/fmp (fixed public REST APIs —
    # only the API key is user-specific); kept True by default so a future
    # self-hosted/configurable-endpoint source can still opt in.
    needs_base_url: bool = True
    # Credential name prefix (<prefix>_api_key / <prefix>_base_url), defaults to the
    # source's registry key. Lets multiple registry entries backed by the same
    # provider account (e.g. "fmp_rating" and "fmp_grades") share one credential
    # ("fmp_api_key") instead of each demanding its own.
    credential_prefix: str | None = None


_SOURCES: dict[str, _Source] = {
    "tradingview": _Source(
        TradingViewConnector,
        "fetch_technicals",
        lambda r: _rating_from_value(r.get("recommendation")),
        "fetch_all_technicals",
    ),
    "finviz": _Source(
        FinvizConnector,
        "fetch_metrics",
        lambda r: _rating_from_value((r.get("metrics") or {}).get("recommendation")),
        "fetch_screener",
    ),
    "finnhub": _Source(
        FinnhubConnector,
        "fetch_recommendation",
        lambda r: rating_from_vote_counts(
            strong_buy=r.get("strongBuy") or 0,
            buy=r.get("buy") or 0,
            hold=r.get("hold") or 0,
            sell=r.get("sell") or 0,
            strong_sell=r.get("strongSell") or 0,
        ),
        requires_credentials=True,
        needs_base_url=False,
    ),
    "fmp_rating": _Source(
        FMPConnector,
        "fetch_rating",
        lambda r: rating_from_overall_score(r.get("overallScore")),
        requires_credentials=True,
        needs_base_url=False,
        credential_prefix="fmp",
    ),
    "fmp_grades": _Source(
        FMPConnector,
        "fetch_grades_consensus",
        lambda r: rating_from_vote_counts(
            strong_buy=r.get("strongBuy") or 0,
            buy=r.get("buy") or 0,
            hold=r.get("hold") or 0,
            sell=r.get("sell") or 0,
            strong_sell=r.get("strongSell") or 0,
        ),
        requires_credentials=True,
        needs_base_url=False,
        credential_prefix="fmp",
    ),
}

SOURCE_NAMES: tuple[str, ...] = tuple(_SOURCES.keys())


def source_requires_credentials(name: str) -> bool:
    """Whether ``name`` needs ``<name>_base_url``/``_api_key`` configured before it's
    usable — used by ``GET /api/v1/signals/sources`` so a credential-free source
    (every one currently wired) is correctly reported as always "configured"."""
    source = _SOURCES.get(name)
    return source.requires_credentials if source is not None else True


class SignalSourceRegistry:
    """Resolves per-source credentials (only for sources that need any) and calls
    the requested connectors for one ticker. ``user_id=None`` resolves
    system-default credentials only (matches ``CredentialManager``'s cascade)."""

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
        ``_fetch_one``'s ``error=`` handling). Sources with no bulk endpoint (e.g.
        finnhub/fmp — ``discover_method=None``) are silently skipped, not errored."""
        names = [n for n in (sources or SOURCE_NAMES) if n in _SOURCES and _SOURCES[n].discover_method]
        results: list[ExternalSignal] = []
        for name in names:
            results.extend(await self._discover_one(name))
        return results

    async def _build_connector(self, name: str, source: _Source) -> Any:
        """Raises ``CredentialNotConfiguredError`` only for a source that actually
        needs credentials and doesn't have them yet."""
        if not source.requires_credentials:
            return source.connector_cls()
        prefix = source.credential_prefix or name
        if not source.needs_base_url:
            # Fixed public API (e.g. finnhub/fmp) — only the API key is user-specific.
            api_key = await self._credentials.get_for_user(f"{prefix}_api_key", self._user_id)
            return source.connector_cls(api_key=api_key)
        base_url = await self._credentials.get_for_user(f"{prefix}_base_url", self._user_id)
        api_key = None
        try:
            api_key = await self._credentials.get_for_user(f"{prefix}_api_key", self._user_id)
        except CredentialNotConfiguredError:
            pass  # optional even for a credentialed source
        return source.connector_cls(base_url, api_key=api_key)

    async def _discover_one(self, name: str) -> list[ExternalSignal]:
        source = _SOURCES[name]
        try:
            connector = await self._build_connector(name, source)
        except CredentialNotConfiguredError:
            return []
        try:
            raw_items = await getattr(connector, source.discover_method)()
            signals = []
            for item in raw_items:
                rating = source.to_rating(item)
                signals.append(
                    ExternalSignal(
                        source=name,
                        ticker=item["ticker"],
                        direction=direction_from_rating(rating),
                        rating=rating,
                        raw=item,
                    )
                )
            return signals
        except Exception as exc:  # noqa: BLE001 - one bad source must not break the rest
            _logger.warning("signal source %s discovery failed: %s", name, exc)
            return []
        finally:
            await connector.aclose()

    async def _fetch_one(self, name: str, ticker: str) -> ExternalSignal:
        source = _SOURCES[name]
        try:
            connector = await self._build_connector(name, source)
        except CredentialNotConfiguredError:
            return ExternalSignal(source=name, ticker=ticker, direction=None, error="not configured")
        try:
            raw = await getattr(connector, source.fetch_method)(ticker)
            rating = source.to_rating(raw)
            return ExternalSignal(
                source=name, ticker=ticker, direction=direction_from_rating(rating), rating=rating, raw=raw
            )
        except Exception as exc:  # noqa: BLE001 - one bad source must not break the rest
            _logger.warning("signal source %s failed for %s: %s", name, ticker, exc)
            return ExternalSignal(source=name, ticker=ticker, direction=None, error=str(exc))
        finally:
            await connector.aclose()


__all__ = ["SOURCE_NAMES", "ExternalSignal", "SignalSourceRegistry", "source_requires_credentials"]
