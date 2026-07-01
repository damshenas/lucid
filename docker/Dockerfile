# syntax=docker/dockerfile:1
# Build context is the repo root (see docker/compose.yml).

# --- Stage 1: build the React UI ---
FROM node:20-alpine AS ui
WORKDIR /ui
COPY src/ui/package.json ./
RUN npm install
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
