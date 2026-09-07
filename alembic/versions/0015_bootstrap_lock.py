"""add bootstrap_lock table

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-07

Single-row sentinel (fixed id=1) that AuthService.bootstrap_first_admin inserts
atomically alongside the first admin user, so two concurrent first-run
``POST /api/v1/auth/setup`` requests can't both succeed (bugs.md finding 8).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_lock",
        sa.Column("id", sa.Integer(), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("bootstrap_lock")
