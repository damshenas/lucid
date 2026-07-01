"""Claude connector — DISABLED placeholder.

Wired up but not called by anything active. A strategy that wants LLM scoring can import
and enable it explicitly. Calls raise ``DisabledConnectorError`` until enabled.
"""

from __future__ import annotations

DISABLED = True
REQUIRED_CONFIG = ["api_key"]
OPTIONAL_CONFIG = {"model": "claude-3-5-sonnet", "temperature": 0.2}


class DisabledConnectorError(RuntimeError):
    pass


class ClaudeClient:
    enabled = False

    def __init__(self, api_key: str | None = None, *, model: str = "claude-3-5-sonnet") -> None:
        self._api_key = api_key
        self._model = model

    async def complete(self, prompt: str) -> str:
        raise DisabledConnectorError("claude connector is disabled")


__all__ = ["ClaudeClient", "DISABLED", "DisabledConnectorError", "OPTIONAL_CONFIG", "REQUIRED_CONFIG"]
