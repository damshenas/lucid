"""M8: signal storage, dedup window, and outcome tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.bus import BuySignalEvent
from src.modules.cache import TTLCache
from src.modules.db.repositories.user import UserRepository
from src.modules.signal import SignalService


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
