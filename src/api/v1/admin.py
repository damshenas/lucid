"""Admin routes: user management (admin only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authentication import AuthError, AuthService
from src.modules.authorization import Permission
from src.modules.com.git import GitError
from src.modules.db.models.base import Role
from src.modules.db.models.user import User
from src.modules.db.repositories.user import UserRepository

from ..deps import get_session, require_permission

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class CreateUserIn(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=72)
    role: Role = Role.viewer


@router.get("/users")
async def list_users(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.manage_users)),
) -> list[dict[str, Any]]:
    users = await UserRepository(session).get_all()
    return [
        {"id": u.id, "username": u.username, "role": u.role, "is_active": u.is_active}
        for u in users
    ]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserIn,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.manage_users)),
) -> dict[str, Any]:
    try:
        user = await AuthService(session).create_user(
            body.username, body.password, body.role.value
        )
        await session.commit()
    except AuthError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"id": user.id, "username": user.username, "role": user.role}


@router.get("/jobs")
async def list_jobs(
    request: Request,
    _: User = Depends(require_permission(Permission.manage_users)),
) -> list[dict[str, Any]]:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        return []
    return [
        {
            "id": job.id,
            "name": job.name,
            "last_run": job.last_run.isoformat() if job.last_run else None,
            "last_status": job.last_status,
            "last_error": job.last_error,
        }
        for job in runtime.scheduler.job_list()
    ]


@router.post("/git-sync")
async def git_sync(
    request: Request,
    _: User = Depends(require_permission(Permission.edit_system_settings)),
) -> dict[str, Any]:
    """On-demand: pull the already-cloned ``EXT_STRATEGIES`` checkout and deploy its
    ``buy``/``sell`` files into the strategies directory. No schedule — admin-triggered
    only, via this endpoint (the "Sync now" button in Settings > Service > Git Sync)."""
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "runtime not available")
    try:
        commit, copied = await runtime.git_sync()
    except GitError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"commit": commit, "deployed": copied}
