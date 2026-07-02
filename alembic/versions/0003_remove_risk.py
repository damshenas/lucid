"""remove risk gate

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-02

The pre-trade risk gate was removed (opt-in artificial trade limits interfered with
validating strategy/algorithm accuracy during testing). Drops the now-unused
``daily_losses`` table; the ``risk`` config section is dropped in code, not the DB.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("daily_losses")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "daily_losses",
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
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("loss_usd", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "day", name="uq_daily_loss_user_day"),
    )
