"""fix position identity: scope uniqueness to open positions + asset_class

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-07

``uq_position_user_ticker`` applied to every position row regardless of status, so
closing a position and buying the same ticker again violated the constraint on
insert (a trader could never complete a second round trip in the same ticker).
It also ignored ``asset_class``, so the same ticker held in two asset classes (e.g.
BTCUSD as both crypto and fx) collided. Replaced with a partial unique index that
only applies to rows where ``status = 'open'`` and includes ``asset_class`` — closed
rows may repeat freely (preserving full history), and the same ticker can be open in
two different asset classes at once.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_position_user_ticker", "positions", type_="unique")
    op.create_index(
        "uq_position_open_user_ticker_assetclass",
        "positions",
        ["user_id", "ticker", "asset_class"],
        unique=True,
        postgresql_where="status = 'open'",
    )


def downgrade() -> None:
    op.drop_index("uq_position_open_user_ticker_assetclass", table_name="positions")
    op.create_unique_constraint("uq_position_user_ticker", "positions", ["user_id", "ticker"])
