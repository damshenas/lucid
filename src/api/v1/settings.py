"""Settings routes: schema-driven config for the current user."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authorization import Permission, has_permission
from src.modules.configs import ConfigError, ConfigPermissionError, validate_settings_values
from src.modules.db.models.user import User
from src.modules.logger import set_level

from ..deps import get_context, get_current_user, get_session

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# Config keys whose new value should take effect immediately instead of waiting for
# the next scheduled `run_strategies` tick (up to `schedule.poll_positions_seconds`,
# default 5 minutes) — see the background-task trigger in save_values() below.
_STRATEGY_ACTIVATION_KEYS = {"strategy.active_buy_strategy", "strategy.active_sell_strategy"}


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
    # Every discovered strategy's config is exposed (not only the active one) so the
    # UI can let a user browse and activate any of them, not just whatever already
    # happens to be active.
    extra = ctx.strategy_service(session).all_extra_sections()
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
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    config = get_context(request).config_service(session)
    if user.must_change_password:
        # This route checks per-key write permission itself (can_write_key) rather
        # than going through require_permission, so it needs its own
        # must_change_password gate too (bugs.md finding 11). Gated behind
        # auth.enforce_password_policy (default off).
        try:
            enforced = bool(await config.resolve("auth.enforce_password_policy"))
        except KeyError:
            enforced = False
        if enforced:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "password change required before this action"
            )
    strategy_service = get_context(request).strategy_service(session)
    # Admins manage "system defaults" (per plan.md's RBAC table) — their writes apply
    # globally (user_id=None) so every trader/viewer picks them up, rather than only
    # affecting the admin's own (trading-disabled) account. A trader's own
    # strategy.* override still lands on their personal user_id.
    target_user_id = None if has_permission(user.role, Permission.edit_system_settings) else user.id
    # Validate the ENTIRE request against the compiled schema before writing
    # anything — an unknown key, a null for a non-nullable field, a wrong type, or
    # an invalid enum choice must reject the whole save, not just the offending key
    # partway through (bugs.md finding 12).
    extra = strategy_service.all_extra_sections()
    schema = await config.compile_schema(
        user_id=target_user_id, asset_class=body.asset_class, extra_sections=extra
    )
    errors = validate_settings_values(schema, body.values)
    if errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "; ".join(errors))
    # A strategy name saved as strategy.active_{buy,sell}_strategy must actually
    # exist and be declared for that direction — otherwise it silently becomes an
    # inert/misdirected "active" strategy with no error anywhere (bugs.md finding 13).
    for direction in ("buy", "sell"):
        strategy_name = body.values.get(f"strategy.active_{direction}_strategy")
        if strategy_name is None:
            continue
        loaded = strategy_service.get_loaded(strategy_name)
        if loaded is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"strategy '{strategy_name}' not found"
            )
        if loaded.direction != direction:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"strategy '{strategy_name}' is a {loaded.direction} strategy, "
                f"cannot set it as the active {direction} strategy",
            )
    try:
        for key, value in body.values.items():
            await config.set_value(
                key, value, role=user.role, user_id=target_user_id, asset_class=body.asset_class
            )
    except ConfigPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    # Apply a changed log level immediately rather than requiring a restart — same
    # LOG_LEVEL-env-wins precedence as startup (src/api/main.py); a value someone
    # set here has no effect if the ops-level env var override is present.
    if "logger.level" in body.values and "LOG_LEVEL" not in os.environ:
        set_level(str(body.values["logger.level"]))
    # A newly activated buy/sell strategy should act on the very next tick, not
    # whenever the scheduled interval next fires — kick off one evaluation pass in
    # the background (never blocks this response on strategy evaluation, which may
    # make real network calls to configured external signal sources).
    if _STRATEGY_ACTIVATION_KEYS.intersection(body.values):
        runtime = getattr(request.app.state, "runtime", None)
        if runtime is not None:
            background_tasks.add_task(runtime.run_strategies)
    return {"ok": True}

