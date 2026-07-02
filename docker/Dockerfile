# syntax=docker/dockerfile:1
# Build context is the repo root (see docker/compose.yml).

# --- Stage 1: build the React UI ---
FROM node:20-alpine AS ui
WORKDIR /ui
COPY src/ui/package.json ./

# Only resolve dependency versions published at least 14 days ago (same freshness
# floor as the Python deps below), to reduce exposure to newly-published or
# newly-compromised package releases. Computed via node (not `date -d`, which
# busybox/alpine's date does not support) for portability across base images.
# Attempt `npm audit fix` (and a forced pass for anything needing a breaking-change
# bump) on a best-effort basis: this is a build-only stage (nothing here ships in
# the final image, see COPY --from=ui below), so remediation is a bonus, not a
# hard gate. Advisories don't always have a fix published >=14 days old (our
# freshness floor), which would otherwise make this step fail non-deterministically
# whenever a fresh, still-unfixable-within-the-window advisory appears. The real
# gates are `npm run build` (fails immediately if a forced bump breaks anything)
# and `python -m pytest` below, same as for the Python side.
RUN NPM_BEFORE="$(node -e 'console.log(new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString())')" && \
    npm install --before "$NPM_BEFORE" && \
    (npm audit fix || true) && \
    (npm audit fix --force || true)
COPY src/ui/ ./
RUN npm run build

# --- Stage 2: Python runtime ---
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install uv via pip (uses the base image's own pip; no extra image pull/installer script).
RUN pip install --no-cache-dir uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY strategies ./strategies
# Second, immutable copy at a path the runtime never bind-mounts over. STRATEGIES_ROOT
# (./strategies) is mounted read-write in production so the git-sync deploy step
# (src/scripts/sync_algorithms.py) can write into it; a fresh/empty mount would
# otherwise hide these built-ins, so they get seeded back in from here at startup.
COPY strategies ./strategies.builtin
COPY alembic ./alembic
COPY alembic.ini ./
COPY tests ./tests

# Only resolve dependency versions published at least 14 days ago, to reduce
# exposure to newly-published or newly-compromised package releases.
RUN uv pip install --system --no-cache \
    --exclude-newer "$(date -u -d '14 days ago' '+%Y-%m-%dT%H:%M:%SZ')" \
    -e ".[dev]"

# Built UI bundle -> served by FastAPI at "/"
COPY --from=ui /ui/dist ./src/ui/dist

# Run the full suite; the build fails if any test fails.
RUN python -m pytest -q

# Non-root runtime user (uid/gid 8686) and writable data dir.
RUN groupadd -g 8686 lucid \
    && useradd -u 8686 -g 8686 -m -s /usr/sbin/nologin lucid \
    && mkdir -p /data \
    && chown -R lucid:lucid /data /app

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER lucid
EXPOSE 8686
ENTRYPOINT ["/entrypoint.sh"]
