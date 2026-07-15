"""Layered configuration: resolution + dynamic schema compilation.

Resolution order (higher wins), per plan.md:
1. ``default.yml``
2. asset-class-scoped DB values   (user_id NULL, asset_class set)
3. global DB values               (user_id NULL, asset_class NULL)
4. per-user DB values             (user_id set; optionally asset-class scoped)

Secrets rule: any key ending in ``_key`` / ``_token`` / ``_secret`` / ``_password``
must never live in YAML or the config store — it belongs in the encrypted credential
store.
"""

from __future__ import annotations

import enum
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from src.conf.schema import LucidConfig
from src.modules.authorization import Permission, has_permission
from src.modules.db.repositories.config import ConfigRepository

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo
    from sqlalchemy.ext.asyncio import AsyncSession

SECRET_WORDS = ("key", "token", "secret", "password")

_MISSING = object()


class ConfigError(Exception):
    """Raised for invalid config operations (e.g. secrets in YAML)."""


class ConfigPermissionError(ConfigError):
    """Raised when a role lacks permission to write a given config key."""


def can_write_key(role: str, key: str) -> bool:
    """Whether ``role`` may write ``key`` at all.

    Per plan.md's RBAC table, admin manages "system defaults" — every section,
    written globally (``user_id=None``; see ``save_values`` in api/v1/settings.py) so
    the change applies to everyone. A trader or analyst may *additionally* override
    their own personal ``strategy.*`` choice (scoped to their own ``user_id``)
    without needing ``edit_system_settings``, since both roles carry
    ``edit_own_strategies``.
    """
    if has_permission(role, Permission.edit_system_settings):
        return True
    section = key.split(".", 1)[0]
    return section == "strategy" and has_permission(role, Permission.edit_own_strategies)


def is_secret_key(key: str) -> bool:
    leaf = key.rsplit(".", 1)[-1].lower()
    last_word = leaf.rsplit("_", 1)[-1]
    return last_word in SECRET_WORDS


def flatten(nested: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in nested.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, f"{dotted}."))
        else:
            out[dotted] = value
    return out


def unflatten(flat: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(".")
        cursor = out
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return out


def load_default_config(path: str | Path) -> dict[str, Any]:
    """Load and validate ``default.yml``. Rejects any secret-looking keys."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    for key in flatten(data):
        if is_secret_key(key):
            raise ConfigError(f"secret key '{key}' must not appear in default.yml")
    LucidConfig.model_validate(data)  # validate shape/types
    return data


@dataclass
class SchemaSection:
    name: str
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)


def _unwrap_optional(annotation: Any) -> Any:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if args:
            return args[0]
    return annotation


def _type_name(annotation: Any) -> str:
    annotation = _unwrap_optional(annotation)
    origin = typing.get_origin(annotation)
    if origin in (list, typing.List):  # noqa: UP006
        return "list"
    if isinstance(annotation, type):
        if issubclass(annotation, bool):
            return "bool"
        if issubclass(annotation, enum.Enum):
            return "enum"
        if issubclass(annotation, int):
            return "int"
        if issubclass(annotation, float):
            return "float"
        if issubclass(annotation, str):
            return "str"
        if issubclass(annotation, list):
            return "list"
    return "str"


def _field_default(info: FieldInfo) -> Any:
    default = info.get_default(call_default_factory=True)
    if default is PydanticUndefined:
        return None
    if isinstance(default, enum.Enum):
        return default.value
    return default


def _choices(annotation: Any) -> list[str] | None:
    """Allowed values for an enum-typed field, so the UI can render a dropdown
    instead of a free-text input (e.g. ``logger.level``, ``execution.quantity_mode``)."""
    annotation = _unwrap_optional(annotation)
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return [item.value for item in annotation]
    return None


def _model_fields(model_cls: type[BaseModel], prefix: str = "") -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, info in model_cls.model_fields.items():
        annotation = _unwrap_optional(info.annotation)
        key = f"{prefix}{name}"
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            out.update(_model_fields(annotation, prefix=f"{key}."))
        else:
            meta: dict[str, Any] = {
                "type": _type_name(info.annotation),
                "default": _field_default(info),
                "required": info.is_required(),
            }
            choices = _choices(info.annotation)
            if choices is not None:
                meta["choices"] = choices
            out[key] = meta
    return out


def module_sections() -> dict[str, dict[str, dict[str, Any]]]:
    """Derive config sections/fields from the LucidConfig Pydantic model."""
    sections: dict[str, dict[str, dict[str, Any]]] = {}
    for name, info in LucidConfig.model_fields.items():
        annotation = _unwrap_optional(info.annotation)
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            sections[name] = _model_fields(annotation)
    return sections


class ConfigService:
    """Resolves layered config and compiles the settings schema.

    Required: ``default_config`` (loaded dict). Optional: ``db_overrides_enabled``.
    """

    def __init__(
        self,
        session: AsyncSession,
        default_config: dict[str, Any],
        *,
        db_overrides_enabled: bool = True,
    ) -> None:
        self._repo = ConfigRepository(session)
        self._defaults = default_config
        self._flat_defaults = flatten(default_config)
        self._db_overrides_enabled = db_overrides_enabled

    @staticmethod
    def _precedence(
        user_id: int | None, asset_class: str | None
    ) -> list[tuple[int | None, str | None]]:
        scopes: list[tuple[int | None, str | None]] = []
        if asset_class is not None:
            scopes.append((None, asset_class))
        scopes.append((None, None))
        if user_id is not None:
            scopes.append((user_id, None))
            if asset_class is not None:
                scopes.append((user_id, asset_class))
        return scopes

    async def resolve(self, key: str, *, user_id: int | None = None, asset_class: str | None = None) -> Any:
        value = self._flat_defaults.get(key, _MISSING)
        if self._db_overrides_enabled:
            for scope_user, scope_ac in self._precedence(user_id, asset_class):
                row = await self._repo.get_scoped(key, user_id=scope_user, asset_class=scope_ac)
                if row is not None:
                    value = row.value
        if value is _MISSING:
            raise KeyError(key)
        return value

    async def compile_values(
        self, *, user_id: int | None = None, asset_class: str | None = None
    ) -> dict[str, Any]:
        flat = dict(self._flat_defaults)
        if self._db_overrides_enabled:
            for scope_user, scope_ac in self._precedence(user_id, asset_class):
                for row in await self._repo.list_scoped(user_id=scope_user, asset_class=scope_ac):
                    flat[row.key] = row.value
        return unflatten(flat)

    async def set_value(
        self,
        key: str,
        value: Any,
        *,
        role: str,
        user_id: int | None = None,
        asset_class: str | None = None,
    ) -> None:
        if is_secret_key(key):
            raise ConfigError(f"'{key}' is a secret; use the credential store, not config")
        if not can_write_key(role, key):
            raise ConfigPermissionError(f"role '{role}' lacks permission to set '{key}'")
        await self._repo.upsert_scoped(key, value, user_id=user_id, asset_class=asset_class)

    async def compile_schema(
        self,
        *,
        user_id: int | None = None,
        asset_class: str | None = None,
        extra_sections: dict[str, dict[str, dict[str, Any]]] | None = None,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Return sections -> fields, each field carrying type/default/required/value.

        ``extra_sections`` folds in active strategy CONFIG_SCHEMA (added in M10). Its
        presence is why the compiled schema changes when the active strategy changes.
        """
        sections = module_sections()
        if extra_sections:
            for section, fields in extra_sections.items():
                sections[section] = dict(fields)

        compiled: dict[str, dict[str, dict[str, Any]]] = {}
        for section, fields in sections.items():
            compiled[section] = {}
            for field_key, meta in fields.items():
                dotted = f"{section}.{field_key}"
                try:
                    value = await self.resolve(dotted, user_id=user_id, asset_class=asset_class)
                except KeyError:
                    value = meta.get("default")
                compiled[section][field_key] = {**meta, "value": value}
        return compiled


__all__ = [
    "ConfigError",
    "ConfigPermissionError",
    "ConfigService",
    "SchemaSection",
    "can_write_key",
    "flatten",
    "is_secret_key",
    "load_default_config",
    "module_sections",
    "unflatten",
]
