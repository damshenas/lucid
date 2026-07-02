#!/usr/bin/env sh
# Apply DB migrations, sync algorithm files, then start Lucid. Built-in strategies are
# scanned by the app lifespan at startup. Access logging is disabled inside the launcher.
set -e

echo "[entrypoint] checking target database exists..."
python -m src.scripts.ensure_database

echo "[entrypoint] applying database migrations..."
alembic upgrade head

echo "[entrypoint] syncing algorithm repo (if configured)..."
# Best-effort: sync_algorithms.py already catches its own errors (bad git config,
# unwritable STRATEGIES_ROOT mount, etc.) and logs+continues rather than raising. This
# guard is defense-in-depth so an unexpected failure here can never take the whole app
# down — worst case it boots with whatever strategies already exist.
python -m src.scripts.sync_algorithms || echo "[entrypoint] algorithm sync step failed, continuing startup"

echo "[entrypoint] starting Lucid on port ${PORT:-8686}..."
exec python -m src.launch
