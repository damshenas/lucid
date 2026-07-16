"""Admin routes: user management (admin only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.conf.schema import AssetClass
from src.modules.authentication import AuthError, AuthService
from src.modules.authentication.password import hash_password
from src.modules.authorization import Permission
from src.modules.com.git import GitError
from src.modules.db.models.base import Role
from src.modules.db.models.user import User
from src.modules.db.repositories.decision import StrategyDecisionRepository
from src.modules.db.repositories.order import OrderRepository
from src.modules.db.repositories.position import PositionRepository
from src.modules.db.repositories.price import PriceFetchAttemptRepository
from src.modules.db.repositories.signal import SignalOutcomeRepository, SignalRepository
from src.modules.db.repositories.user import UserRepository
from src.modules.encryption import CredentialNotConfiguredError
from src.modules.price import storage

from ..deps import get_context, get_session, require_permission
from .positions import sync_positions_from_broker

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class CreateUserIn(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=72)
    role: Role = Role.analyst


class UpdateUserIn(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=72)


class ResetTradingDataIn(BaseModel):
    user_id: int | None = None
    asset_class: str = AssetClass.equity.value
    sync_from_broker: bool = True


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


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserIn,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.manage_users)),
) -> dict[str, Any]:
    repo = UserRepository(session)
    target = await repo.get_by_id(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    updates: dict[str, Any] = {}
    if body.role is not None:
        updates["role"] = body.role.value
    if body.is_active is not None:
        if body.is_active is False and target.role == Role.admin.value:
            others = await repo.get_all()
            active_admins = [
                u for u in others if u.role == Role.admin.value and u.is_active and u.id != target.id
            ]
            if not active_admins:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "cannot deactivate the last active admin"
                )
        updates["is_active"] = body.is_active

    target = await repo.update(target, **updates)
    await session.commit()
    return {
        "id": target.id,
        "username": target.username,
        "role": target.role,
        "is_active": target.is_active,
    }


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    body: ResetPasswordIn,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.manage_users)),
) -> dict[str, bool]:
    repo = UserRepository(session)
    target = await repo.get_by_id(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    await repo.update(
        target,
        password_hash=hash_password(body.new_password),
        must_change_password=True,
        failed_login_attempts=0,
        locked_until=None,
    )
    await session.commit()
    return {"ok": True}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_permission(Permission.manage_users)),
) -> None:
    if user_id == acting_user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot delete your own account")
    repo = UserRepository(session)
    target = await repo.get_by_id(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if target.role == Role.admin.value:
        others = await repo.get_all()
        other_admins = [u for u in others if u.role == Role.admin.value and u.id != target.id]
        if not other_admins:
            raise HTTPException(status.HTTP_409_CONFLICT, "cannot delete the last admin")
    await repo.delete(target)
    await session.commit()


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


@router.get("/reports/price-coverage")
async def price_coverage_report(
    request: Request,
    _: User = Depends(require_permission(Permission.manage_users)),
) -> list[dict[str, Any]]:
    """Per (ticker, interval): earliest/latest stored bar and row count — computed
    on demand straight from the Parquet files, no DB table needed."""
    storage_path = get_context(request).settings.price.storage_path
    rows: list[dict[str, Any]] = []
    for interval in storage.list_intervals(storage_path):
        for ticker in storage.list_tickers(storage_path, interval):
            df = storage.read_bars(storage_path, ticker, interval)
            if df is None or df.empty:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "interval": interval,
                    "earliest": df.index.min().isoformat(),
                    "latest": df.index.max().isoformat(),
                    "bar_count": len(df),
                }
            )
    return sorted(rows, key=lambda r: (r["ticker"], r["interval"]))


@router.get("/reports/fetch-activity")
async def fetch_activity_report(
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=30),
    _: User = Depends(require_permission(Permission.manage_users)),
) -> list[dict[str, Any]]:
    """Every price-fetch attempt (success or failure) in the last ``days`` days —
    an append-only log, unlike the "last fetched" upsert row in ``price_fetch_log``."""
    attempts = await PriceFetchAttemptRepository(session).list_recent(days=days)
    return [
        {
            "ticker": a.ticker,
            "interval": a.interval,
            "attempted_at": a.attempted_at.isoformat() if a.attempted_at else None,
            "status": a.status,
            "error_message": a.error_message,
            "duration_seconds": a.duration_seconds,
            "rows_fetched": a.rows_fetched,
        }
        for a in attempts
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


@router.post("/reset-trading-data")
async def reset_trading_data(
    request: Request,
    body: ResetTradingDataIn,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.manage_trading_data)),
) -> dict[str, Any]:
    """Danger-zone "start fresh" reset: hard-deletes a trader's (or, when ``user_id``
    is omitted, every trader's) positions, orders, signals, signal outcomes and
    strategy-decision log. Never touches users, credentials, watchlist, or config/
    settings — only trade history and its derived state. When ``sync_from_broker``
    (default ``True``), each reset user's *current* broker holdings are re-synced
    into ``positions`` right after the wipe (the same reconciliation ``POST
    /api/v1/positions/sync`` performs), so the app reflects reality immediately
    instead of showing zero positions until the next manual sync. A broker/
    credential failure for one user is recorded per-user in the response rather than
    failing the whole request — the wipe itself always completes."""
    ctx = get_context(request)
    user_repo = UserRepository(session)
    if body.user_id is not None:
        target = await user_repo.get_by_id(body.user_id)
        if target is None or target.role != Role.trader.value:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "trader not found")
        targets = [target]
    else:
        targets = [u for u in await user_repo.get_all() if u.role == Role.trader.value]

    reset_counts: dict[str, dict[str, int]] = {}
    for user in targets:
        # Delete signal_outcomes before signals (FK signal_outcomes.signal_id ->
        # signals.id) — order.position_id/signal_id are ON DELETE SET NULL so orders
        # can be wiped in any order relative to positions/signals.
        orders_deleted = await OrderRepository(session).delete_all_for_user(user.id)
        outcomes_deleted = await SignalOutcomeRepository(session).delete_all_for_user(user.id)
        signals_deleted = await SignalRepository(session).delete_all_for_user(user.id)
        decisions_deleted = await StrategyDecisionRepository(session).delete_all_for_user(user.id)
        positions_deleted = await PositionRepository(session).delete_all_for_user(user.id)
        reset_counts[user.username] = {
            "orders": orders_deleted,
            "signal_outcomes": outcomes_deleted,
            "signals": signals_deleted,
            "decisions": decisions_deleted,
            "positions": positions_deleted,
        }
    await session.commit()

    sync_results: dict[str, Any] = {}
    if body.sync_from_broker:
        for user in targets:
            try:
                sync_results[user.username] = await sync_positions_from_broker(
                    ctx, session, user.id, body.asset_class
                )
            except CredentialNotConfiguredError as exc:
                sync_results[user.username] = {"error": str(exc)}
            except Exception as exc:  # noqa: BLE001
                sync_results[user.username] = {"error": str(exc)}
        await session.commit()

    return {"reset": reset_counts, "synced": sync_results}
