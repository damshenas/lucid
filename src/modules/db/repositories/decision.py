"""Strategy decision log repository."""

from __future__ import annotations

from sqlalchemy import delete, select

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

    async def delete_all_for_user(self, user_id: int) -> int:
        """Hard-delete every decision-log row for a user — used by the admin "reset
        trading data" endpoint (src/api/v1/admin.py). Returns the number of rows
        removed."""
        result = await self.session.execute(
            delete(StrategyDecisionLog).where(StrategyDecisionLog.user_id == user_id)
        )
        await self.session.flush()
        return int(result.rowcount or 0)
