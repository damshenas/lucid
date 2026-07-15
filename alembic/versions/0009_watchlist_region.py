"""add price_watchlist.region

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-15

Adds a per-ticker market-hours region ("us"/"eu"/"em", default "us") used by the new
multi-region market-hours gating (see src/modules/schedules/market_hours.py and
TradingRuntime._watchlist_by_poll_interval/.run_strategies in src/api/runtime.py) —
mirrors the poll_interval column added in migration 0006.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_watchlist",
        sa.Column("region", sa.String(10), nullable=False, server_default="us"),
    )
    op.create_check_constraint(
        "ck_price_watchlist_region",
        "price_watchlist",
        "region IN ('us', 'eu', 'em')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_price_watchlist_region", "price_watchlist", type_="check")
    op.drop_column("price_watchlist", "region")
