"""Create the target Postgres database if it does not already exist.

Runs before ``alembic upgrade head`` in the Docker entrypoint. Lucid is often
pointed at a shared Postgres instance (see docker/compose.yml) where only the
server-level role/user is guaranteed to exist, not the app's own database.
Connects to the ``postgres`` maintenance database on the same server to check
for / create the target database, then exits. No-op for non-Postgres URLs
(e.g. the sqlite URL used by tests).
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

from sqlalchemy.engine import make_url

# Postgres identifiers are limited to 63 bytes; restrict to a conservative safe
# subset so the name can never break out of the double-quoted identifier below.
_SAFE_DBNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


async def ensure_database(database_url: str) -> None:
    try:
        url = make_url(database_url)
    except Exception as exc:  # noqa: BLE001 - malformed URL is a skip, not a crash
        print(f"[ensure_database] could not parse DATABASE_URL, skipping: {exc}")
        return

    if url.get_backend_name() != "postgresql":
        print("[ensure_database] DATABASE_URL is not postgresql+asyncpg://..., skipping.")
        return

    dbname = url.database or ""
    if not _SAFE_DBNAME_RE.match(dbname):
        print(
            f"[ensure_database] database name {dbname!r} failed safety validation, skipping."
        )
        return

    import asyncpg

    conn = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port or 5432,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", dbname)
        if exists:
            print(f"[ensure_database] database '{dbname}' already exists.")
            return
        print(f"[ensure_database] database '{dbname}' not found, creating...")
        try:
            await conn.execute(f'CREATE DATABASE "{dbname}"')
            print(f"[ensure_database] database '{dbname}' created.")
        except asyncpg.DuplicateDatabaseError:
            # Another instance created it concurrently; nothing to do.
            print(f"[ensure_database] database '{dbname}' was just created by another process.")
    finally:
        await conn.close()


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("[ensure_database] DATABASE_URL is not set, skipping.", file=sys.stderr)
        return
    asyncio.run(ensure_database(database_url))


if __name__ == "__main__":
    main()
