"""In-memory TTL cache.

Not a Redis replacement — a simple in-process dict with expiry, used for signal dedup
windows and avoiding redundant price fetches within a scheduler cycle.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    """Time-to-live cache with a maximum entry count.

    Optional: ``default_ttl_seconds``, ``max_entries``.
    """

    def __init__(self, default_ttl_seconds: float = 300.0, max_entries: int = 10_000) -> None:
        self._default_ttl = default_ttl_seconds
        self._max_entries = max_entries
        self._store: OrderedDict[Any, tuple[float, Any]] = OrderedDict()

    def _now(self) -> float:
        return time.monotonic()

    def _purge_expired(self) -> None:
        now = self._now()
        expired = [k for k, (exp, _) in self._store.items() if exp <= now]
        for key in expired:
            self._store.pop(key, None)

    def _evict_if_needed(self) -> None:
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)  # oldest insertion

    def get(self, key: Any, default: Any = None) -> Any:
        item = self._store.get(key)
        if item is None:
            return default
        expiry, value = item
        if expiry <= self._now():
            self._store.pop(key, None)
            return default
        return value

    def set(self, key: Any, value: Any, ttl: float | None = None) -> None:
        ttl = self._default_ttl if ttl is None else ttl
        self._store[key] = (self._now() + ttl, value)
        self._store.move_to_end(key)
        self._evict_if_needed()

    def add_if_absent(self, key: Any, value: Any = True, ttl: float | None = None) -> bool:
        """Set the key only if not already present/live. Returns True if it was added.

        Useful for dedup: the first caller within the window gets ``True``, duplicates
        get ``False``.
        """
        if self.__contains__(key):
            return False
        self.set(key, value, ttl)
        return True

    def delete(self, key: Any) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def __contains__(self, key: Any) -> bool:
        item = self._store.get(key)
        if item is None:
            return False
        if item[0] <= self._now():
            self._store.pop(key, None)
            return False
        return True

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._store)


__all__ = ["TTLCache"]
