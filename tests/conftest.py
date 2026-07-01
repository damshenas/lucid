"""Shared pytest fixtures. Uses in-memory SQLite — no external services."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.db.connection import Database
from src.modules.db.models import Base


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest_asyncio.fixture
async def session(db: Database) -> AsyncIterator[AsyncSession]:
    async with db.session() as s:
        yield s
