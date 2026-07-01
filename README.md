# Lucid

Automated trading platform. Python + FastAPI backend, React (Vite) frontend, PostgreSQL,
Parquet price storage, single hardened Docker container on port 8686.

See [docs/milestones.md](docs/milestones.md) for the implementation plan.

## Quickstart (development)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# run tests (in-memory sqlite, no external services)
pytest

# run the API locally
uvicorn src.api.main:create_app --factory --reload --port 8686
```

## Required environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/lucid` |
| `LUCID_ENCRYPTION_KEY` | base64 32-byte key for AES-256-GCM secret storage |
| `LUCID_JWT_SECRET` | random string for signing JWTs |
| `BIND_IFACE` / `BIND_IP` | optional — lock outbound traffic to a NIC |

Secrets are never stored in YAML. `src/conf/default.yml` holds non-sensitive defaults only.

## Layout

- `src/modules/` — reusable functionality (bus, db, configs, broker, execution, price, …)
- `src/conf/` — layered config (`default.yml` + Pydantic `schema.py`)
- `src/api/` — FastAPI routes (`/api/v1/*`) and the `create_app()` factory
- `src/ui/` — React + Vite SPA
- `strategies/buy/`, `strategies/sell/` — single-file strategies
- `alembic/` — database migrations
- `docker/` — container build and hardening
