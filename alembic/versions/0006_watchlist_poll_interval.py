"""add price_watchlist.poll_interval

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-06

Adds the per-ticker intraday polling granularity ("1m" or "1h", default "1h") used
by the redesigned Watchlist UI (Settings > Price > Watchlist) — see
src/modules/db/models/price.py and TradingRuntime._watchlist_by_poll_interval /
.register_jobs in src/api/runtime.py. Independent of the always-on daily ("1d")
fetch every watchlist ticker still gets regardless of this value.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_watchlist",
        sa.Column("poll_interval", sa.String(10), nullable=False, server_default="1h"),
    )
    op.create_check_constraint(
        "ck_price_watchlist_poll_interval",
        "price_watchlist",
        "poll_interval IN ('1m', '1h')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_price_watchlist_poll_interval", "price_watchlist", type_="check")
    op.drop_column("price_watchlist", "poll_interval")
