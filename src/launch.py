"""Process launcher.

Applies NIC binding (if configured) at process start, then runs uvicorn with access
logging disabled so client IPs are never written to logs.
"""

from __future__ import annotations

import os

from src.modules.netbind import apply as apply_netbind

_VALID_UVICORN_LEVELS = {"critical", "error", "warning", "info", "debug", "trace"}
_DEBUG_LEVELS = {"debug", "trace"}


def main() -> None:
    apply_netbind()
    import uvicorn

    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    if log_level not in _VALID_UVICORN_LEVELS:
        log_level = "info"

    http: str | type = "auto"
    if log_level in _DEBUG_LEVELS:
        # Only swap in the debug HTTP protocol when actually debugging — it adds a
        # small amount of per-connection overhead and is a no-op otherwise.
        from src.modules.httpdebug import DebugH11Protocol

        http = DebugH11Protocol

    uvicorn.run(
        "src.api.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container binds all interfaces; exposure is controlled by the host
        port=int(os.environ.get("PORT", "8686")),
        access_log=False,
        log_level=log_level,
        http=http,
    )


if __name__ == "__main__":
    main()
