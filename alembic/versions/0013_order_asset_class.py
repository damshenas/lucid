"""add orders.asset_class

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-07

Needed so a pending order can be reconciled later without guessing which broker to
query — ExecutionEngine.reconcile_pending_orders (bugs.md finding 2) resolves the
broker for ``(order.user_id, order.asset_class)`` directly from the order row
instead of via its (possibly still-nonexistent, for a not-yet-filled buy) position.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("asset_class", sa.String(20), nullable=False, server_default="equity"),
    )
    op.alter_column("orders", "asset_class", server_default=None)


def downgrade() -> None:
    op.drop_column("orders", "asset_class")
