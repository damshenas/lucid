"""add strategy_decisions table

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-06

Adds the ``strategy_decisions`` log — one row per *change* in a strategy's
evaluation outcome for a (user, ticker), whether or not it acted. Powers the
"why or why not" decision list on each active strategy's page (see
src/modules/db/models/decision.py, src/api/runtime.py).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("ticker", sa.String(30), nullable=False, index=True),
        sa.Column("asset_class", sa.String(20), nullable=False, server_default="equity"),
        sa.Column("strategy_name", sa.String(150), nullable=False, index=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("acted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reasoning", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("strategy_decisions")
