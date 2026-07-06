"""Strategy decision log repository."""

from __future__ import annotations

from sqlalchemy import select

from ..models.decision import StrategyDecisionLog
from .base import BaseRepository


class StrategyDecisionRepository(BaseRepository[StrategyDecisionLog]):
    model = StrategyDecisionLog

    async def latest_for(
        self, user_id: int, ticker: str, strategy_name: str
    ) -> StrategyDecisionLog | None:
        stmt = (
            select(StrategyDecisionLog)
            .where(
                StrategyDecisionLog.user_id == user_id,
                StrategyDecisionLog.ticker == ticker,
                StrategyDecisionLog.strategy_name == strategy_name,
            )
            .order_by(StrategyDecisionLog.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_strategy(
        self, user_id: int, strategy_name: str, *, limit: int = 50, offset: int = 0
    ) -> list[StrategyDecisionLog]:
        stmt = (
            select(StrategyDecisionLog)
            .where(
                StrategyDecisionLog.user_id == user_id,
                StrategyDecisionLog.strategy_name == strategy_name,
            )
            .order_by(StrategyDecisionLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
