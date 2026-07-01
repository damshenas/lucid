"""Settings routes: schema-driven config for the current user."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.configs import ConfigError
from src.modules.db.models.user import User

from ..deps import get_context, get_current_user, get_session

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class SettingsIn(BaseModel):
    values: dict[str, Any]  # dotted key -> value
    asset_class: str | None = None


@router.get("/schema")
async def get_schema(
    request: Request,
    asset_class: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ctx = get_context(request)
    config = ctx.config_service(session)
    values = await config.compile_values(user_id=user.id, asset_class=asset_class)
    extra = ctx.strategy_service(session).active_extra_sections(values)
    return await config.compile_schema(user_id=user.id, asset_class=asset_class, extra_sections=extra)


@router.get("")
async def get_values(
    request: Request,
    asset_class: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    config = get_context(request).config_service(session)
    return await config.compile_values(user_id=user.id, asset_class=asset_class)


@router.post("")
async def save_values(
    request: Request,
    body: SettingsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    config = get_context(request).config_service(session)
    try:
        for key, value in body.values.items():
            await config.set_value(key, value, user_id=user.id, asset_class=body.asset_class)
    except ConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return {"ok": True}
