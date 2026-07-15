"""add price_fetch_attempts

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-15

Append-only log of every price-fetch attempt (success or failure), unlike the
upsert-style ``price_fetch_log`` (only the most recent success per ticker/interval).
Powers the new admin "fetch activity" report — see
src/modules/db/repositories/price.py::PriceFetchAttemptRepository and
GET /api/v1/admin/reports/fetch-activity.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_fetch_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(30), nullable=False),
        sa.Column("interval", sa.String(20), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rows_fetched", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_price_fetch_attempts_ticker", "price_fetch_attempts", ["ticker"])
    op.create_index("ix_price_fetch_attempts_attempted_at", "price_fetch_attempts", ["attempted_at"])


def downgrade() -> None:
    op.drop_index("ix_price_fetch_attempts_attempted_at", table_name="price_fetch_attempts")
    op.drop_index("ix_price_fetch_attempts_ticker", table_name="price_fetch_attempts")
    op.drop_table("price_fetch_attempts")
