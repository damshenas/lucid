"""FastAPI dependencies: context access, sessions, auth, and permission guards."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authentication import TokenError
from src.modules.authorization import Permission, has_permission
from src.modules.db.models.user import User
from src.modules.db.repositories.user import UserRepository

from .context import AppContext

_bearer = HTTPBearer(auto_error=False)


def get_context(request: Request) -> AppContext:
    return request.app.state.context


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    ctx = get_context(request)
    async with ctx.db.session() as session:
        yield session


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    ctx = get_context(request)
    try:
        payload = ctx.token_service.decode(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    async with ctx.db.session() as session:
        user = await UserRepository(session).get_by_id(int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid user")
    return user


def require_permission(permission: Permission) -> Callable[..., object]:
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient permissions")
        return user

    return dependency
