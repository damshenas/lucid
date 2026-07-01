"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-01

Greenfield baseline: creates every table from the ORM metadata so the migration and
the models never drift. Subsequent changes use ``alembic revision --autogenerate``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from src.modules.db.models import Base

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
