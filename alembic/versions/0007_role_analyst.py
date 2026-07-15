"""replace viewer role with analyst

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-15

The ``viewer`` role is replaced by ``analyst`` (view trading data + manage/activate own
strategies, but cannot trade or manage credentials) — see src/modules/db/models/base.py
(Role enum) and src/modules/authorization/__init__.py (ROLE_PERMISSIONS). ``role`` is
stored as ``String(20)``, not a native DB enum, so this is a pure data migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


users = sa.table("users", sa.column("role", sa.String))


def upgrade() -> None:
    op.execute(users.update().where(users.c.role == "viewer").values(role="analyst"))


def downgrade() -> None:
    op.execute(users.update().where(users.c.role == "analyst").values(role="viewer"))
