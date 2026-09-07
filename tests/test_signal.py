"""M8: signal storage, dedup window, and outcome tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.bus import BuySignalEvent
from src.modules.cache import TTLCache
from src.modules.db.repositories.user import UserRepository
from src.modules.encryption import CredentialManager, Encryptor, generate_key
from src.modules.signal import SignalService
from src.modules.signal import sources as sources_module
from src.modules.signal.rating import direction_from_rating, rating_from_score, rating_from_text
from src.modules.signal.sources import ExternalSignal, SignalSourceRegistry, _Source


def _encryptor() -> Encryptor:
    import base64

    return Encryptor(base64.b64decode(generate_key()))


async def _user(session: AsyncSession) -> int:
    user = await UserRepository(session).create(username="u", password_hash="x")
    return user.id


async def test_store_from_event(session: AsyncSession) -> None:
    uid = await _user(session)
    svc = SignalService(session)
    signal = await svc.store_from_event(
        BuySignalEvent(ticker="AAPL", user_id=uid, source="strat", confidence=0.8)
    )
    assert signal.direction == "buy"
    assert signal.status == "new"


async def test_dedup_within_window(session: AsyncSession) -> None:
    uid = await _user(session)
    svc = SignalService(session, dedup_window_seconds=300)

    assert await svc.is_duplicate(uid, "AAPL", "buy") is False
    signal = await svc.store(user_id=uid, ticker="AAPL", direction="buy", source="s")
    await svc.mark_acted(signal)
    assert await svc.is_duplicate(uid, "AAPL", "buy") is True


async def test_dedup_outside_window(session: AsyncSession) -> None:
    uid = await _user(session)
    svc = SignalService(session, dedup_window_seconds=300)
    signal = await svc.store(user_id=uid, ticker="AAPL", direction="buy", source="s")
    await svc.mark_acted(signal)
    # push the action time outside the window
    await SignalService(session)._repo.update(
        signal, acted_at=datetime.now(timezone.utc) - timedelta(seconds=1000)
    )
    assert await svc.is_duplicate(uid, "AAPL", "buy") is False


async def test_dedup_uses_cache(session: AsyncSession) -> None:
    uid = await _user(session)
    cache = TTLCache()
    svc = SignalService(session, cache=cache, dedup_window_seconds=300)
    signal = await svc.store(user_id=uid, ticker="AAPL", direction="buy", source="s")
    await svc.mark_acted(signal)
    assert f"sig:{uid}:AAPL:buy" in cache
    assert await svc.is_duplicate(uid, "AAPL", "buy") is True


async def test_record_outcome(session: AsyncSession) -> None:
    uid = await _user(session)
    svc = SignalService(session)
    signal = await svc.store(user_id=uid, ticker="AAPL", direction="buy", source="s")

    await svc.record_outcome(signal_id=signal.id, user_id=uid, pnl=42.0)
    outcomes = await svc._outcomes.get_all()
    assert len(outcomes) == 1
    assert outcomes[0].profitable is True
    assert outcomes[0].pnl == 42.0


class _FakeConnector:
    """Stand-in for a real com.* connector — same shape (base_url/api_key/client
    constructor args, an async fetch method, ``aclose``) without any network call."""

    def __init__(self, base_url: str, *, api_key: str | None = None, client=None) -> None:
        self.base_url = base_url
        self.api_key = api_key

    async def fetch_rank(self, ticker: str) -> dict:
        return {"rank": 1, "ticker": ticker}

    async def fetch_ranks(self) -> list[dict]:
        return [{"rank": 1, "ticker": "AAPL"}, {"rank": 4, "ticker": "TSLA"}]

    async def aclose(self) -> None:
        pass


class _FailingConnector(_FakeConnector):
    async def fetch_rank(self, ticker: str) -> dict:
        raise RuntimeError("boom")

    async def fetch_ranks(self) -> list[dict]:
        raise RuntimeError("boom")


def _fake_rating(raw: dict) -> str | None:
    # Mirrors Zacks Rank's own 1(Strong Buy)-5(Strong Sell) scale — just a stand-in
    # normalization function so these tests don't depend on any real connector.
    return {1: "strong_buy", 2: "buy", 3: "neutral", 4: "sell", 5: "strong_sell"}.get(raw.get("rank"))


# A fake *credentialed* source (requires_credentials=True) — every currently-wired
# real source (finviz/tradingview) needs zero credentials, but the registry must
# still correctly gate a source that does, for any future authenticated source.
_FAKE_SOURCE_NAME = "acme"


async def test_source_not_configured_returns_error_not_raise(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FakeConnector, "fetch_rank", _fake_rating, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    registry = SignalSourceRegistry(mgr, user_id=None)
    results = await registry.fetch("AAPL", [_FAKE_SOURCE_NAME])
    assert results == [
        ExternalSignal(source=_FAKE_SOURCE_NAME, ticker="AAPL", direction=None, error="not configured")
    ]


async def test_source_normalizes_rating_once_configured(
    session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FakeConnector, "fetch_rank", _fake_rating, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    await mgr.set_for_user(f"{_FAKE_SOURCE_NAME}_base_url", "https://acme.test", user_id=None)

    result = (await SignalSourceRegistry(mgr, user_id=None).fetch("AAPL", [_FAKE_SOURCE_NAME]))[0]

    assert result == ExternalSignal(
        source=_FAKE_SOURCE_NAME,
        ticker="AAPL",
        direction="buy",
        rating="strong_buy",
        raw={"rank": 1, "ticker": "AAPL"},
    )


async def test_source_error_is_captured_not_raised(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FailingConnector, "fetch_rank", _fake_rating, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    await mgr.set_for_user(f"{_FAKE_SOURCE_NAME}_base_url", "https://acme.test", user_id=None)

    result = (await SignalSourceRegistry(mgr, user_id=None).fetch("AAPL", [_FAKE_SOURCE_NAME]))[0]

    assert result.direction is None
    assert result.error == "boom"


async def test_registry_discover_aggregates_every_source_ticker(
    session: AsyncSession, monkeypatch
) -> None:
    """discover() is the bulk counterpart to fetch() — one call per source (not per
    ticker), returning every ticker that source currently has an opinion on,
    normalized the same way fetch() would per-ticker."""
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FakeConnector, "fetch_rank", _fake_rating, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    await mgr.set_for_user(f"{_FAKE_SOURCE_NAME}_base_url", "https://acme.test", user_id=None)

    results = await SignalSourceRegistry(mgr, user_id=None).discover([_FAKE_SOURCE_NAME])

    assert results == [
        ExternalSignal(
            source=_FAKE_SOURCE_NAME,
            ticker="AAPL",
            direction="buy",
            rating="strong_buy",
            raw={"rank": 1, "ticker": "AAPL"},
        ),
        ExternalSignal(
            source=_FAKE_SOURCE_NAME,
            ticker="TSLA",
            direction="sell",
            rating="sell",
            raw={"rank": 4, "ticker": "TSLA"},
        ),
    ]


async def test_registry_discover_skips_unconfigured_source(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FakeConnector, "fetch_rank", _fake_rating, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    assert await SignalSourceRegistry(mgr, user_id=None).discover([_FAKE_SOURCE_NAME]) == []


async def test_registry_discover_swallows_connector_failure(
    session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FailingConnector, "fetch_rank", _fake_rating, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    await mgr.set_for_user(f"{_FAKE_SOURCE_NAME}_base_url", "https://acme.test", user_id=None)

    assert await SignalSourceRegistry(mgr, user_id=None).discover([_FAKE_SOURCE_NAME]) == []


async def test_registry_discover_dedupes_same_ticker_from_one_source(
    session: AsyncSession, monkeypatch
) -> None:
    """Regression test for bugs.md finding 14: one provider reporting the same
    normalized ticker twice (e.g. two exchange listings) must count as a single
    opinion, not two — first occurrence wins."""

    class _DuplicateTickerConnector(_FakeConnector):
        async def fetch_ranks(self) -> list[dict]:
            return [{"rank": 1, "ticker": "AAPL"}, {"rank": 5, "ticker": "AAPL"}]

    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_DuplicateTickerConnector, "fetch_rank", _fake_rating, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    await mgr.set_for_user(f"{_FAKE_SOURCE_NAME}_base_url", "https://acme.test", user_id=None)

    results = await SignalSourceRegistry(mgr, user_id=None).discover([_FAKE_SOURCE_NAME])

    assert len(results) == 1
    assert results[0].rating == "strong_buy"  # the first (rank=1) row, not the second


def test_direction_from_rating_parses_text_and_numeric() -> None:
    assert rating_from_text("Strong Buy") == "strong_buy"
    assert rating_from_text("strong sell") == "strong_sell"
    assert rating_from_text("Hold") == "neutral"
    assert rating_from_score(0.6) == "strong_buy"
    assert rating_from_score(-0.6) == "strong_sell"
    assert rating_from_score(0.0) == "neutral"
    assert rating_from_score(None) is None
    assert rating_from_text(None) is None
    assert rating_from_text("unrelated text") is None
    assert direction_from_rating("strong_buy") == "buy"
    assert direction_from_rating("sell") == "sell"
    assert direction_from_rating("neutral") == "hold"
    assert direction_from_rating(None) is None


def test_fake_source_direction_maps_rank_to_buy_sell_hold() -> None:
    assert _fake_rating({"rank": 1}) == "strong_buy"
    assert _fake_rating({"rank": 2}) == "buy"
    assert _fake_rating({"rank": 3}) == "neutral"
    assert _fake_rating({"rank": 4}) == "sell"
    assert _fake_rating({"rank": 5}) == "strong_sell"
    assert _fake_rating({"rank": None}) is None
