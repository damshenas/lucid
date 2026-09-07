"""add positions.high_water_mark

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-07

Backfilled to avg_price for existing open positions so an already-open position
doesn't suddenly compare its stop against NULL (trailing_stop.py falls back to
avg_price for a NULL row anyway, but backfilling avoids a one-time "reset to
entry" the moment this ships against a position that's already run up)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("positions", sa.Column("high_water_mark", sa.Float(), nullable=True))
    op.execute("UPDATE positions SET high_water_mark = avg_price WHERE status = 'open'")


def downgrade() -> None:
    op.drop_column("positions", "high_water_mark")
