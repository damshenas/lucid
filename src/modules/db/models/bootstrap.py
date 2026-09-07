"""Single-row sentinel that makes first-run admin bootstrap atomic.

Inserting this fixed-PK row (id=1) as part of the same transaction that creates the
first admin is what actually serializes two concurrent ``POST /api/v1/auth/setup``
requests — the count-then-create check in AuthService.bootstrap_first_admin alone is
a plain read-then-write race, not an atomic one (bugs.md finding 8). Whichever
request's insert commits first wins; the loser gets a database-level unique/PK
violation instead of both successfully creating an admin.
"""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BootstrapLock(Base):
    __tablename__ = "bootstrap_lock"

    id: Mapped[int] = mapped_column(primary_key=True)
