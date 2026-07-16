"""Role-based access control.

Roles and permissions (per plan.md):

| Role    | Trading | Settings              | User Mgmt |
|---------|---------|------------------------|-----------|
| admin   | No      | System defaults       | Yes       |
| trader  | Yes     | Own creds + strategies| No        |
| analyst | No      | Own strategies only   | No        |

Note: ``admin`` administers the system and users but does not place trades.
``analyst`` can view trading data and manage/activate strategies (e.g. for
research) but cannot place trades or manage credentials.
"""

from __future__ import annotations

from enum import Enum

from src.modules.db.models.base import Role


class Permission(str, Enum):
    trade = "trade"
    view_trading = "view_trading"
    manage_users = "manage_users"
    edit_system_settings = "edit_system_settings"
    edit_own_credentials = "edit_own_credentials"
    edit_own_strategies = "edit_own_strategies"
    change_password = "change_password"
    manage_trading_data = "manage_trading_data"


ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    Role.admin.value: {
        Permission.manage_users,
        Permission.edit_system_settings,
        Permission.change_password,
        Permission.manage_trading_data,
    },
    Role.trader.value: {
        Permission.trade,
        Permission.view_trading,
        Permission.edit_own_credentials,
        Permission.edit_own_strategies,
        Permission.change_password,
    },
    Role.analyst.value: {
        Permission.view_trading,
        Permission.edit_own_strategies,
        Permission.change_password,
    },
}


class PermissionDenied(Exception):
    """Raised when a role lacks a required permission."""


def has_permission(role: str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_permission(role: str, permission: Permission) -> None:
    if not has_permission(role, permission):
        raise PermissionDenied(f"role '{role}' lacks permission '{permission.value}'")


def can_trade(role: str) -> bool:
    return has_permission(role, Permission.trade)


def can_manage_users(role: str) -> bool:
    return has_permission(role, Permission.manage_users)


def can_edit_system_settings(role: str) -> bool:
    return has_permission(role, Permission.edit_system_settings)


__all__ = [
    "ROLE_PERMISSIONS",
    "Permission",
    "PermissionDenied",
    "can_edit_system_settings",
    "can_manage_users",
    "can_trade",
    "has_permission",
    "require_permission",
]
