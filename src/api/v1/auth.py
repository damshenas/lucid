"""Auth routes: first-run setup, login, refresh, password change."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authentication import (
    AccountLockedError,
    AuthService,
    FirstRunError,
    InvalidCredentialsError,
    TokenError,
)
from src.modules.db.models.user import User
from src.modules.db.repositories.user import UserRepository

from ..deps import get_context, get_current_user, get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class SetupIn(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool = False
    # Whether the server currently enforces must_change_password (auth.
    # enforce_password_policy, off by default) — lets the UI decide whether to
    # force the change-password screen instead of blindly always forcing it.
    password_policy_enforced: bool = False


class RefreshIn(BaseModel):
    refresh_token: str


class ChangePasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=72)


async def _issue_tokens(request: Request, session: AsyncSession, user: User) -> TokenOut:
    ctx = get_context(request)
    tokens = ctx.token_service
    try:
        enforced = bool(await ctx.config_service(session).resolve("auth.enforce_password_policy"))
    except KeyError:
        enforced = False
    return TokenOut(
        access_token=tokens.create_access_token(str(user.id), role=user.role),
        refresh_token=tokens.create_refresh_token(str(user.id)),
        must_change_password=user.must_change_password,
        password_policy_enforced=enforced,
    )


@router.get("/status")
async def status_(session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    return {"initialized": await AuthService(session).has_any_user()}


@router.post("/setup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def setup(request: Request, body: SetupIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    try:
        user = await AuthService(session).bootstrap_first_admin(body.username, body.password)
        await session.commit()
    except FirstRunError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return await _issue_tokens(request, session, user)


@router.post("/login", response_model=TokenOut)
async def login(request: Request, body: LoginIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    try:
        user = await AuthService(session).authenticate(body.username, body.password)
    except AccountLockedError as exc:
        await session.commit()  # persist the lock state check itself causing no change
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except InvalidCredentialsError as exc:
        # Commit even on failure: the failed-attempt counter/lockout set by
        # authenticate() must persist, otherwise lockout never triggers.
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    await session.commit()
    return await _issue_tokens(request, session, user)


@router.post("/refresh", response_model=TokenOut)
async def refresh(request: Request, body: RefreshIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    tokens = get_context(request).token_service
    try:
        payload = tokens.decode(body.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = await UserRepository(session).get_by_id(int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid user")
    return await _issue_tokens(request, session, user)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    stored = await UserRepository(session).get_by_id(user.id)
    await AuthService(session).change_password(stored, body.new_password)
    await session.commit()
    return {"ok": True}
