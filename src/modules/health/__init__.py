"""Liveness and readiness probes.

These endpoints are intentionally silent in normal logs (they run below the configured
log threshold). ``/health/ready`` verifies the database is reachable.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
async def ready(request: Request) -> dict[str, str]:
    ctx = request.app.state.context
    try:
        async with ctx.db.session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unreachable") from exc
    return {"status": "ready"}
