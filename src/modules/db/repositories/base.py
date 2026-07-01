"""Generic async repository."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """CRUD + pagination over one model. Subclasses set ``model``.

    Callers control transaction boundaries; methods ``flush`` but do not ``commit``.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id_: Any) -> ModelT | None:
        return await self.session.get(self.model, id_)

    async def get_all(self) -> list[ModelT]:
        result = await self.session.execute(select(self.model))
        return list(result.scalars().all())

    async def create(self, **values: Any) -> ModelT:
        obj = self.model(**values)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: ModelT, **values: Any) -> ModelT:
        for key, value in values.items():
            setattr(obj, key, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(self.model))
        return int(result.scalar_one())

    async def paginate(self, *, limit: int = 50, offset: int = 0) -> list[ModelT]:
        stmt = select(self.model).order_by(self.model.id).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
