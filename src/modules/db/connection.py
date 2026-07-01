"""Async engine and session factory.

Handles both PostgreSQL (production) and in-memory SQLite (unit tests). SQLite gets a
``StaticPool`` with a shared connection so an ``:memory:`` schema persists across
sessions; pool sizing options apply only to real server databases.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


class Database:
    """Owns the async engine and produces sessions.

    Required: ``database_url``.
    Optional: ``pool_size``, ``max_overflow``, ``echo``.
    """

    def __init__(
        self,
        database_url: str,
        *,
        pool_size: int = 5,
        max_overflow: int = 10,
        echo: bool = False,
    ) -> None:
        self.database_url = database_url
        if database_url.startswith("sqlite"):
            self._engine: AsyncEngine = create_async_engine(
                database_url,
                echo=echo,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        else:
            self._engine = create_async_engine(
                database_url,
                echo=echo,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=True,
            )
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    def session(self) -> AsyncSession:
        """Return a new session. Use as an async context manager."""
        return self._sessionmaker()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Session scoped to a transaction — commits on success, rolls back on error."""
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self._engine.dispose()
