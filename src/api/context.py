"""Application composition root.

``AppContext`` builds and holds the shared collaborators (DB, config, auth, encryption,
bus, brokers, strategies) and exposes small factories for per-request services. It is
created once in the FastAPI lifespan and stored on ``app.state.context``.

Env vars are read when present; for local/dev they fall back to safe ephemeral values so
the app still boots (a warning is logged). Production must set them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.conf.schema import LucidConfig
from src.modules.authentication import TokenService
from src.modules.broker import BrokerRegistry
from src.modules.broker.base import Broker
from src.modules.bus import EventBus
from src.modules.com.trading212 import Trading212Broker, Trading212Client
from src.modules.configs import ConfigService, load_default_config
from src.modules.db.connection import Database
from src.modules.encryption import (
    ENV_VAR as ENCRYPTION_KEY_ENV_VAR,
)
from src.modules.encryption import (
    CredentialManager,
    CredentialNotConfiguredError,
    Encryptor,
    generate_key,
    load_key_from_env,
)
from src.modules.logger import get_logger
from src.modules.strategy import StrategyRegistryService

_logger = get_logger("api.context")

_DEFAULT_SQLITE = "sqlite+aiosqlite:///:memory:"
_DEFAULT_CONFIG_PATH = "src/conf/default.yml"
_DEFAULT_STRATEGIES_ROOT = "strategies"
_DEFAULT_EXT_STRATEGIES_ROOT = "ext_strategies"


@dataclass
class AppContext:
    db: Database
    config_defaults: dict
    settings: LucidConfig
    token_service: TokenService
    encryptor: Encryptor
    bus: EventBus
    broker_registry: BrokerRegistry
    strategies_root: str
    ext_strategies_root: str

    @property
    def is_sqlite(self) -> bool:
        return self.db.database_url.startswith("sqlite")

    # -- per-request service factories -------------------------------------

    def config_service(self, session) -> ConfigService:
        return ConfigService(session, self.config_defaults)

    def credential_manager(self, session) -> CredentialManager:
        return CredentialManager(session, self.encryptor)

    def strategy_service(self, session) -> StrategyRegistryService:
        return StrategyRegistryService(session, self.strategies_root)

    async def resolve_broker(self, session, user_id: int, asset_class: str) -> Broker:
        values = await self.config_service(session).compile_values(
            user_id=user_id, asset_class=asset_class
        )
        broker_cfg = values.get("broker", {})
        broker_name = broker_cfg.get("broker_name", "trading212")
        paper_mode = bool(broker_cfg.get("paper_mode", True))
        if paper_mode:
            return self.broker_registry.resolve(
                broker_name=broker_name, asset_class=asset_class, paper_mode=True
            )
        creds = self.credential_manager(session)
        try:
            api_key = await creds.get_for_user("trading212_api_key", user_id)
            base_url = await creds.get_for_user("trading212_base_url", user_id)
        except CredentialNotConfiguredError as exc:
            raise CredentialNotConfiguredError(
                "live broker requires trading212 credentials"
            ) from exc
        return self.broker_registry.resolve(
            broker_name=broker_name,
            asset_class=asset_class,
            paper_mode=False,
            api_key=api_key,
            base_url=base_url,
        )

    # -- construction ------------------------------------------------------

    @classmethod
    def build(
        cls,
        *,
        database_url: str | None = None,
        config_path: str = _DEFAULT_CONFIG_PATH,
        strategies_root: str | None = None,
        ext_strategies_root: str | None = None,
    ) -> AppContext:
        database_url = database_url or os.environ.get("DATABASE_URL")
        if not database_url:
            _logger.warning("DATABASE_URL not set — using in-memory SQLite (dev only)")
            database_url = _DEFAULT_SQLITE

        strategies_root = strategies_root or os.environ.get(
            "STRATEGIES_ROOT", _DEFAULT_STRATEGIES_ROOT
        )
        ext_strategies_root = ext_strategies_root or os.environ.get(
            "EXT_STRATEGIES", _DEFAULT_EXT_STRATEGIES_ROOT
        )

        jwt_secret = os.environ.get("LUCID_JWT_SECRET")
        if not jwt_secret:
            _logger.warning("LUCID_JWT_SECRET not set — using an ephemeral dev secret")
            jwt_secret = generate_key()

        if not os.environ.get(ENCRYPTION_KEY_ENV_VAR):
            _logger.warning("LUCID_ENCRYPTION_KEY not set — using an ephemeral dev key")
            import base64

            encryptor = Encryptor(base64.b64decode(generate_key()))
        else:
            # Set but invalid (bad base64, wrong length) must fail startup rather than
            # silently falling back to a random key — that would make previously
            # encrypted credentials permanently undecryptable and, with multiple
            # replicas, each instance would mint a different key.
            encryptor = Encryptor(load_key_from_env())

        config_defaults = load_default_config(config_path)
        settings = LucidConfig.model_validate(config_defaults)

        broker_registry = BrokerRegistry()
        broker_registry.register(
            "trading212",
            "equity",
            lambda **kw: Trading212Broker(
                Trading212Client(kw["api_key"], kw["base_url"])
            ),
        )

        return cls(
            db=Database(database_url),
            config_defaults=config_defaults,
            settings=settings,
            token_service=TokenService(jwt_secret, access_expiry_minutes=30),
            encryptor=encryptor,
            bus=EventBus(),
            broker_registry=broker_registry,
            strategies_root=strategies_root,
            ext_strategies_root=ext_strategies_root,
        )
