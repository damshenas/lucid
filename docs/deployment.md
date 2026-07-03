# Lucid — Deployment

Single hardened container, single port (default 8686). FastAPI serves the API and the
built React bundle. PostgreSQL runs alongside; Parquet price data and logs live on a
volume.

## Required environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/lucid` |
| `LUCID_ENCRYPTION_KEY` | base64 32-byte key for AES-256-GCM secrets |
| `LUCID_JWT_SECRET` | random string for signing JWTs |
| `STRATEGIES_ROOT` | strategy directory (default `/strategies` in the container) |
| `BIND_IFACE` / `BIND_IP` | optional — lock outbound traffic to a NIC |
| `PORT` | optional — listen port (default 8686) |

Generate an encryption key:

```python
python -c "from src.modules.encryption import generate_key; print(generate_key())"
```

## Build & run

```bash
export LUCID_ENCRYPTION_KEY=... LUCID_JWT_SECRET=...
cd docker
docker compose build     # runs the full test suite; build fails on any failure
docker compose up -d
docker compose logs -f lucid
```

Startup sequence (entrypoint):

```
alembic upgrade head  →  python -m src.launch (applies NIC binding, starts uvicorn --no-access-log)
```

Built-in strategies are scanned and upserted by the app lifespan on startup.

## Hardening (compose)

- Non-root user `lucid` (uid/gid 8686)
- `read_only: true` root filesystem
- `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`
- `tmpfs: /tmp, /run`
- Volumes: `lucid_data → /data` (Parquet prices, DB data dir), `../strategies → /strategies`
- Access logging disabled — client IPs never written to logs

## Host preparation (rootless Podman / SELinux)

```bash
sudo bash docker/prepare.sh /container/lucid
```

Creates the data directory, chowns it to the subuid mapping (108685), and applies the
`container_file_t` SELinux label.

### Algorithm git sync (optional)

To enable the "Sync now" button (Settings > Service > Git Sync), clone the algorithm
repo into `ext-strategies` yourself, with whatever remote/branch you want — the app
only ever runs `git pull` in it, never a clone:

```bash
git clone --branch <branch> <repo-url> /container/lucid/ext-strategies
sudo bash docker/prepare.sh /container/lucid   # re-chown — see below
```

Re-running `prepare.sh` is required after cloning (or any out-of-band `git`
operation in that directory): its files are owned by whatever host user ran `git
clone`, not the container's subuid-mapped runtime user, and the app's `git pull`
fails with `Permission denied` writing `.git/FETCH_HEAD` until they're chowned to
match.

## First run

1. Open `http://<host>:8686/`.
2. Create the first admin (allowed only while no users exist).
3. Add credentials and a watchlist; set active buy/sell strategies in Settings.
```
