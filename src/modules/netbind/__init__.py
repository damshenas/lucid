"""Socket-level NIC binding to lock outbound traffic to a specific interface/IP.

Set ``BIND_IFACE`` (uses ``SO_BINDTODEVICE`` — needs ``CAP_NET_RAW``) or ``BIND_IP``
(source-IP bind — needs host networking). Applied at process start so every HTTP client
is covered. Loopback traffic is never redirected.
"""

from __future__ import annotations

import os
import socket

from src.modules.logger import get_logger

_logger = get_logger("netbind")
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex


def _is_loopback(address: object) -> bool:
    try:
        host = address[0]  # type: ignore[index]
    except (TypeError, IndexError, KeyError):
        return False
    return host in ("127.0.0.1", "::1", "localhost")


def _bind(sock: socket.socket) -> None:
    iface = os.environ.get("BIND_IFACE")
    ip = os.environ.get("BIND_IP")
    if iface and hasattr(socket, "SO_BINDTODEVICE"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, iface.encode() + b"\0")
        except OSError as exc:
            _logger.warning("SO_BINDTODEVICE failed for %s: %s", iface, exc)
    elif ip:
        try:
            sock.bind((ip, 0))
        except OSError as exc:
            _logger.warning("source-IP bind failed for %s: %s", ip, exc)


def apply() -> bool:
    """Patch socket connect to bind outbound sockets. Returns True if binding is active."""
    iface = os.environ.get("BIND_IFACE")
    ip = os.environ.get("BIND_IP")
    if not iface and not ip:
        return False

    def connect(self: socket.socket, address):  # type: ignore[no-untyped-def]
        if not _is_loopback(address):
            _bind(self)
        return _original_connect(self, address)

    def connect_ex(self: socket.socket, address):  # type: ignore[no-untyped-def]
        if not _is_loopback(address):
            _bind(self)
        return _original_connect_ex(self, address)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    _logger.info("outbound traffic bound to %s", iface or ip)
    return True


__all__ = ["apply"]
