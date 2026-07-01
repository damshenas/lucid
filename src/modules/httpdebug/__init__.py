"""Optional debug-only detail for uvicorn's "Invalid HTTP request received." warning.

Uvicorn's H11Protocol logs a bare warning with no detail whenever h11 raises
``RemoteProtocolError`` while parsing a connection (malformed request line, bad
headers, a TLS handshake landing on the plaintext port, etc.) — the underlying
exception message is never surfaced. This wraps the h11 ``Connection.next_event``
bound method (a stable h11 API, not uvicorn's internal request-handling loop) to log
that message at DEBUG level, then re-raises so uvicorn's own warning + 400 response
path runs unchanged. Never logs the client address (per the project's "no client IP
in logs" rule) — only the h11 exception message itself.
"""

from __future__ import annotations

import logging

import h11
from uvicorn.protocols.http.h11_impl import H11Protocol

_logger = logging.getLogger("uvicorn.error")


class DebugH11Protocol(H11Protocol):
    def connection_made(self, transport) -> None:  # type: ignore[no-untyped-def]
        super().connection_made(transport)
        original_next_event = self.conn.next_event

        def next_event_with_logging():  # type: ignore[no-untyped-def]
            try:
                return original_next_event()
            except h11.RemoteProtocolError as exc:
                _logger.debug("Invalid HTTP request detail: %s", exc)
                raise

        self.conn.next_event = next_event_with_logging  # type: ignore[method-assign]
