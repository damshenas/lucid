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

_URL_RE = re.compile(
    r"^postgresql\+asyncpg://(?P<user>[^:]+):(?P<password>[^@]+)@"
    r"(?P<host>[^:/]+):(?P<port>\d+)/(?P<dbname>.+)$"
)


async def ensure_database(database_url: str) -> None:
    match = _URL_RE.match(database_url)
    if not match:
        print("[ensure_database] DATABASE_URL is not postgresql+asyncpg://..., skipping.")
        return

    import asyncpg

    user = match.group("user")
    password = match.group("password")
    host = match.group("host")
    port = int(match.group("port"))
    dbname = match.group("dbname")

    conn = await asyncpg.connect(
        user=user, password=password, host=host, port=port, database="postgres"
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
