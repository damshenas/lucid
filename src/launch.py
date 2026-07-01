"""Process launcher.

Applies NIC binding (if configured) at process start, then runs uvicorn with access
logging disabled so client IPs are never written to logs.
"""

from __future__ import annotations

import os

from src.modules.netbind import apply as apply_netbind


def main() -> None:
    apply_netbind()
    import uvicorn

    uvicorn.run(
        "src.api.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container binds all interfaces; exposure is controlled by the host
        port=int(os.environ.get("PORT", "8686")),
        access_log=False,
    )


if __name__ == "__main__":
    main()
