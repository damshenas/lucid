"""One-shot startup sync: seed built-in strategies, then pull the algorithm repo into
the staging mount and deploy.

Run by ``docker/entrypoint.sh`` after migrations but before the app starts.
``STRATEGIES_ROOT`` is a writable-but-ephemeral directory (a tmpfs mount in
production, see docker/compose.yml) that starts empty on every container start, so
this always: (1) seeds it from the image's baked-in ``BUILTIN_STRATEGIES_ROOT``
(``/app/strategies`` — never mounted over, always available), then (2) always attempts
to pull the already-cloned ``EXT_STRATEGIES`` checkout (remote/branch configured
out-of-band on the host) and copy its ``buy``/``sell`` files on top — a no-op (best
effort, logged and skipped) when ``EXT_STRATEGIES`` isn't a git checkout at all. The
app only ever scans ``STRATEGIES_ROOT`` — it never runs code directly out of
``EXT_STRATEGIES`` — see ``src.modules.com.git.deploy_strategies``. Beyond this startup
run, syncing is on-demand only, triggered by an admin via
``POST /api/v1/admin/git-sync`` — there is no recurring schedule and no separate
enable/disable setting; both run unconditionally, safe because a missing checkout is
handled gracefully.
"""

from __future__ import annotations

import asyncio
import os

from src.modules.com.git import GitError, sync_and_deploy
from src.modules.logger import get_logger
from src.modules.strategy import seed_missing_strategies

_logger = get_logger("scripts.sync_algorithms")

_DEFAULT_STRATEGIES_ROOT = "strategies"
_DEFAULT_EXT_STRATEGIES_ROOT = "ext_strategies"


async def main() -> None:
    ext_strategies_root = os.environ.get("EXT_STRATEGIES", _DEFAULT_EXT_STRATEGIES_ROOT)
    strategies_root = os.environ.get("STRATEGIES_ROOT", _DEFAULT_STRATEGIES_ROOT)

    # STRATEGIES_ROOT is a writable-but-ephemeral directory (tmpfs in production —
    # empty on every container start) so the git-sync deploy target is never the
    # read-only image layer. Seed it from the image's baked-in built-in strategies
    # first, without ever overwriting a file already there (a git sync always wins
    # on conflict, since it runs after this).
    #
    # This whole step is best-effort: an unwritable STRATEGIES_ROOT must never
    # prevent the app from starting. Worst case the app boots with whatever
    # strategies already exist there (possibly none, discoverable/fixable via POST
    # /api/v1/strategies/scan once fixed), rather than not booting at all.
    builtin_root = os.environ.get("BUILTIN_STRATEGIES_ROOT", _DEFAULT_STRATEGIES_ROOT)
    try:
        seeded = seed_missing_strategies(builtin_root, strategies_root)
        if seeded:
            _logger.info("seeded %d built-in strategy file(s) into %s", len(seeded), strategies_root)
    except OSError as exc:
        _logger.error(
            "could not seed built-in strategies into %s — check that STRATEGIES_ROOT "
            "is writable (see docker/compose.yml's tmpfs mounts): %s",
            strategies_root,
            exc,
        )

    try:
        commit, copied = await sync_and_deploy(
            staging_root=ext_strategies_root,
            target_root=strategies_root,
        )
    except (GitError, OSError) as exc:
        _logger.error("git sync failed, continuing startup with existing strategies: %s", exc)
        return

    _logger.info("startup git sync complete at %s (%d file(s) updated)", commit[:8], len(copied))


if __name__ == "__main__":
    asyncio.run(main())
