"""Broker registry: resolve the active broker for a user/asset-class.

One active broker per user. When ``paper_mode`` is set, a ``PaperBroker`` is returned
regardless of the configured broker name. Real brokers are registered per asset class
(or under the ``"*"`` wildcard).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import Broker, BrokerNotRegisteredError
from .paper import PaperBroker

BrokerFactory = Callable[..., Broker]
_WILDCARD = "*"
_PAPER = "paper"


class BrokerRegistry:
    def __init__(self) -> None:
        self._factories: dict[tuple[str, str], BrokerFactory] = {}
        # Paper broker available for every asset class by default.
        self.register(
            _PAPER,
            _WILDCARD,
            lambda **kw: PaperBroker(
                starting_cash=kw.get("starting_cash", 100_000.0),
                price_provider=kw.get("price_provider"),
            ),
        )

    def register(self, broker_name: str, asset_class: str, factory: BrokerFactory) -> None:
        self._factories[(broker_name, asset_class)] = factory

    def _lookup(self, broker_name: str, asset_class: str) -> BrokerFactory:
        factory = self._factories.get((broker_name, asset_class))
        if factory is None:
            factory = self._factories.get((broker_name, _WILDCARD))
        if factory is None:
            raise BrokerNotRegisteredError(
                f"no broker '{broker_name}' registered for asset class '{asset_class}'"
            )
        return factory

    def resolve(
        self,
        *,
        broker_name: str,
        asset_class: str,
        paper_mode: bool = False,
        **factory_kwargs: Any,
    ) -> Broker:
        name = _PAPER if paper_mode else broker_name
        return self._lookup(name, asset_class)(**factory_kwargs)
