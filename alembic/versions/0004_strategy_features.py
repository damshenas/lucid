"""add strategy_registry.features

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-03

Adds a ``features`` JSON column to ``strategy_registry``, populated from each
strategy file's own module-level ``FEATURES`` list (e.g. ``trend_follow``
declares ``["signals"]``). Drives which per-strategy sidebar page sections the UI
shows (see src/modules/strategy/loader.py and pages/StrategyDetail.tsx).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_registry",
        sa.Column("features", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strategy_registry", "features")
