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


def _fake_direction(raw: dict) -> str | None:
    # Mirrors the old Zacks-rank mapping (1/2=buy, 3=hold, 4/5=sell) — just a stand-in
    # normalization function so these tests don't depend on any real connector.
    rank = raw.get("rank")
    if rank in (1, 2):
        return "buy"
    if rank in (4, 5):
        return "sell"
    return "hold" if rank == 3 else None


# A fake *credentialed* source (requires_credentials=True) — every currently-wired
# real source (finviz/tradingview) needs zero credentials, but the registry must
# still correctly gate a source that does, for any future authenticated source.
_FAKE_SOURCE_NAME = "acme"


async def test_source_not_configured_returns_error_not_raise(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FakeConnector, "fetch_rank", _fake_direction, "fetch_ranks", requires_credentials=True),
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
        _Source(_FakeConnector, "fetch_rank", _fake_direction, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    await mgr.set_for_user(f"{_FAKE_SOURCE_NAME}_base_url", "https://acme.test", user_id=None)

    result = (await SignalSourceRegistry(mgr, user_id=None).fetch("AAPL", [_FAKE_SOURCE_NAME]))[0]

    assert result == ExternalSignal(
        source=_FAKE_SOURCE_NAME, ticker="AAPL", direction="buy", raw={"rank": 1, "ticker": "AAPL"}
    )


async def test_source_error_is_captured_not_raised(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FailingConnector, "fetch_rank", _fake_direction, "fetch_ranks", requires_credentials=True),
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
        _Source(_FakeConnector, "fetch_rank", _fake_direction, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    await mgr.set_for_user(f"{_FAKE_SOURCE_NAME}_base_url", "https://acme.test", user_id=None)

    results = await SignalSourceRegistry(mgr, user_id=None).discover([_FAKE_SOURCE_NAME])

    assert results == [
        ExternalSignal(
            source=_FAKE_SOURCE_NAME, ticker="AAPL", direction="buy", raw={"rank": 1, "ticker": "AAPL"}
        ),
        ExternalSignal(
            source=_FAKE_SOURCE_NAME, ticker="TSLA", direction="sell", raw={"rank": 4, "ticker": "TSLA"}
        ),
    ]


async def test_registry_discover_skips_unconfigured_source(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FakeConnector, "fetch_rank", _fake_direction, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    assert await SignalSourceRegistry(mgr, user_id=None).discover([_FAKE_SOURCE_NAME]) == []


async def test_registry_discover_swallows_connector_failure(
    session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setitem(
        sources_module._SOURCES,
        _FAKE_SOURCE_NAME,
        _Source(_FailingConnector, "fetch_rank", _fake_direction, "fetch_ranks", requires_credentials=True),
    )
    mgr = CredentialManager(session, _encryptor())
    await mgr.set_for_user(f"{_FAKE_SOURCE_NAME}_base_url", "https://acme.test", user_id=None)

    assert await SignalSourceRegistry(mgr, user_id=None).discover([_FAKE_SOURCE_NAME]) == []


def test_direction_from_rating_parses_text_and_numeric() -> None:
    parse = sources_module._direction_from_rating
    assert parse("Strong Buy") == "buy"
    assert parse("strong_sell") == "sell"
    assert parse("Hold") == "hold"
    assert parse(0.5) == "buy"
    assert parse(-0.5) == "sell"
    assert parse(0.0) == "hold"
    assert parse(None) is None
    assert parse("unrelated text") is None


def test_fake_source_direction_maps_rank_to_buy_sell_hold() -> None:
    assert _fake_direction({"rank": 1}) == "buy"
    assert _fake_direction({"rank": 2}) == "buy"
    assert _fake_direction({"rank": 3}) == "hold"
    assert _fake_direction({"rank": 4}) == "sell"
    assert _fake_direction({"rank": 5}) == "sell"
    assert _fake_direction({"rank": None}) is None
