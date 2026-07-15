"""add position profit-tier tracking

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-15

Adds ``profit_tier1_taken``/``profit_tier2_taken`` so a tiered sell strategy (e.g. the
rewritten ``strategies/sell/trailing_stop.py``) never re-fires the same profit-take
tier twice for the same open position — see
src/modules/db/models/position.py, PositionRepository.mark_tier_taken, and
SellSignalEvent.profit_tier / ExecutionEngine.handle_sell.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "positions",
        sa.Column("profit_tier1_taken", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "positions",
        sa.Column("profit_tier2_taken", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("positions", "profit_tier2_taken")
    op.drop_column("positions", "profit_tier1_taken")
