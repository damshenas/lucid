"""fix missing server defaults on strategy_decisions timestamps

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-16

``strategy_decisions`` (migration 0005) was hand-written instead of generated from
the ORM metadata (unlike 0001's greenfield ``Base.metadata.create_all``) and its
``created_at``/``updated_at`` columns were created ``nullable=False`` with no
``server_default`` — unlike every other table's timestamp columns, and unlike what
``TimestampMixin`` (``src/modules/db/models/base.py``) actually declares
(``server_default=func.now()``). Every INSERT that doesn't explicitly set these
(e.g. ``BaseRepository.create()``, used by ``StrategyDecisionRepository`` /
``TradingRuntime._record_decision``) relies entirely on the DB applying that
default — without it, every recorded strategy decision fails with
``NotNullViolationError: null value in column "created_at"``. Tests never caught
this because the sqlite test DB is built straight from ``Base.metadata`` (see
tests/conftest.py), which already has the correct server_default baked in.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("strategy_decisions", "created_at", server_default=sa.text("now()"))
    op.alter_column("strategy_decisions", "updated_at", server_default=sa.text("now()"))


def downgrade() -> None:
    op.alter_column("strategy_decisions", "created_at", server_default=None)
    op.alter_column("strategy_decisions", "updated_at", server_default=None)
