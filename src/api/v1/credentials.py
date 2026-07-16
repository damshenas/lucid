"""Platform credential routes: system-level (admin) and per-user (trader) API keys.

Credentials are stored ciphertext-only via ``CredentialManager``/``CredentialRepository``
(see ``modules/encryption``). Values are write-only over this API — only a boolean
"configured" flag is ever returned, never the plaintext or ciphertext.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.authorization import Permission
from src.modules.db.models.user import User
from src.modules.db.repositories.credential import CredentialRepository
from src.modules.db.repositories.user import UserRepository

from ..deps import get_context, get_session, require_permission

router = APIRouter(prefix="/api/v1/credentials", tags=["credentials"])

# Keys manageable through this API, grouped by platform so the UI can render one
# section per platform inside a single Credentials tab. Extend here when a new
# integration needs a platform credential — the credential store itself accepts any
# string key. "platform" is a display grouping only, not used for authorization.
CREDENTIAL_CATALOG: list[dict[str, Any]] = [
    {
        "key": "trading212_key_id",
        "label": "API Key",
        "platform": "Trading212",
        "secret": True,
    },
    {
        "key": "trading212_secret_key",
        "label": "API Secret",
        "platform": "Trading212",
        "secret": True,
    },
    # Trading212 authenticates via HTTP Basic auth over this key_id/secret_key pair
    # (see Trading212Client). Which account it hits is chosen via the "Paper mode"
    # toggle (broker.paper_mode), not a user-supplied base URL — see
    # src/modules/com/trading212 DEMO_BASE_URL / LIVE_BASE_URL.
    # External signal-source connectors (src/modules/signal/sources.py) — a source
    # only participates (for a strategy's EXTERNAL_SOURCES, or the manual
    # POST /api/v1/signals/sources/check) once its base_url credential is set here;
    # api_key is optional (depends on the provider).
    *(
        item
        for platform, key_prefix in (
            ("Finviz", "finviz"),
            ("TradingView", "tradingview"),
            ("Zacks", "zacks"),
            ("Barchart", "barchart"),
        )
        for item in (
            {"key": f"{key_prefix}_base_url", "label": "Base URL", "platform": platform, "secret": False},
            {"key": f"{key_prefix}_api_key", "label": "API Key", "platform": platform, "secret": True},
        )
    ),
]
_KNOWN_KEYS = {item["key"] for item in CREDENTIAL_CATALOG}


class CredentialIn(BaseModel):
    key: str
    value: str = Field(min_length=1)


class UseDefaultIn(BaseModel):
    use_default_credentials: bool


def _require_known_key(key: str) -> None:
    if key not in _KNOWN_KEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown credential key '{key}'")


async def _catalog_status(repo: CredentialRepository, user_id: int | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in CREDENTIAL_CATALOG:
        row = await repo.get(item["key"], user_id)
        out.append({**item, "configured": row is not None})
    return out


@router.get("/system")
async def get_system_credentials(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.edit_system_settings)),
) -> list[dict[str, Any]]:
    return await _catalog_status(CredentialRepository(session), None)


@router.post("/system", status_code=status.HTTP_204_NO_CONTENT)
async def set_system_credential(
    body: CredentialIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.edit_system_settings)),
) -> None:
    _require_known_key(body.key)
    await get_context(request).credential_manager(session).set_for_user(
        body.key, body.value, user_id=None
    )
    await session.commit()


@router.get("/mine")
async def get_my_credentials(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.edit_own_credentials)),
) -> dict[str, Any]:
    credentials = await _catalog_status(CredentialRepository(session), user.id)
    return {"use_default_credentials": user.use_default_credentials, "credentials": credentials}


@router.post("/mine", status_code=status.HTTP_204_NO_CONTENT)
async def set_my_credential(
    body: CredentialIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.edit_own_credentials)),
) -> None:
    _require_known_key(body.key)
    await get_context(request).credential_manager(session).set_for_user(
        body.key, body.value, user_id=user.id
    )
    await session.commit()


@router.patch("/mine/use-default", status_code=status.HTTP_204_NO_CONTENT)
async def set_use_default_credentials(
    body: UseDefaultIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.edit_own_credentials)),
) -> None:
    # `user` was loaded on get_current_user's own short-lived session (see deps.py),
    # not this request-scoped `session` — refetch here before updating, same pattern
    # as auth.change_password.
    repo = UserRepository(session)
    stored = await repo.get_by_id(user.id)
    await repo.update(stored, use_default_credentials=body.use_default_credentials)
    await session.commit()
