"""M1: database foundation — models, base repository CRUD + pagination."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.db.models import Base
from src.modules.db.repositories import UserRepository


def test_all_tables_registered() -> None:
    expected = {
        "users",
        "credentials",
        "positions",
        "orders",
        "signals",
        "signal_outcomes",
        "app_logs",
        "strategy_registry",
        "user_config",
        "price_watchlist",
        "price_fetch_log",
    }
    assert expected <= set(Base.metadata.tables)


async def test_base_repository_crud(session: AsyncSession) -> None:
    repo = UserRepository(session)

    created = await repo.create(username="alice", password_hash="x", role="trader")
    assert created.id is not None

    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.username == "alice"

    await repo.update(created, role="admin")
    assert (await repo.get_by_id(created.id)).role == "admin"

    assert await repo.count() == 1

    await repo.delete(created)
    assert await repo.get_by_id(created.id) is None
    assert await repo.count() == 0


async def test_base_repository_pagination(session: AsyncSession) -> None:
    repo = UserRepository(session)
    for i in range(5):
        await repo.create(username=f"user{i}", password_hash="x")

    page1 = await repo.paginate(limit=2, offset=0)
    page2 = await repo.paginate(limit=2, offset=2)
    assert [u.username for u in page1] == ["user0", "user1"]
    assert [u.username for u in page2] == ["user2", "user3"]
    assert await repo.count() == 5


async def test_get_by_username(session: AsyncSession) -> None:
    repo = UserRepository(session)
    await repo.create(username="bob", password_hash="x")
    found = await repo.get_by_username("bob")
    assert found is not None and found.username == "bob"
    assert await repo.get_by_username("missing") is None
