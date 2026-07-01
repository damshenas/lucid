"""Auth routes: first-run setup, login, refresh, password change."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authentication import (
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
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class RefreshIn(BaseModel):
    refresh_token: str


class ChangePasswordIn(BaseModel):
    new_password: str


def _issue_tokens(request: Request, user: User) -> TokenOut:
    tokens = get_context(request).token_service
    return TokenOut(
        access_token=tokens.create_access_token(str(user.id), role=user.role),
        refresh_token=tokens.create_refresh_token(str(user.id)),
        must_change_password=user.must_change_password,
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
    return _issue_tokens(request, user)


@router.post("/login", response_model=TokenOut)
async def login(request: Request, body: LoginIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    try:
        user = await AuthService(session).authenticate(body.username, body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return _issue_tokens(request, user)


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
    return _issue_tokens(request, user)


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
