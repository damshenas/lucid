"""Telegram connector — DISABLED placeholder.

No notification dispatcher exists yet. ``notify`` is inert (logs at debug and returns
False) so nothing active depends on it.
"""

from __future__ import annotations

from src.modules.logger import get_logger

DISABLED = True
REQUIRED_CONFIG = ["bot_token", "chat_id"]
OPTIONAL_CONFIG: dict[str, object] = {}

_logger = get_logger("com.telegram")


class TelegramClient:
    enabled = False

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    async def notify(self, message: str) -> bool:
        _logger.debug("telegram disabled; dropped message: %s", message)
        return False


__all__ = ["DISABLED", "OPTIONAL_CONFIG", "REQUIRED_CONFIG", "TelegramClient"]
