"""One-shot startup sync: seed built-in strategies, then pull the algorithm repo into
the staging mount and deploy.

Run by ``docker/entrypoint.sh`` after migrations but before the app starts.
``STRATEGIES_ROOT`` is a writable-but-ephemeral directory (a tmpfs mount in
production, see docker/compose.yml) that starts empty on every container start, so
this always: (1) seeds it from the image's baked-in ``BUILTIN_STRATEGIES_ROOT``
(``/app/strategies`` — never mounted over, always available), then (2) if git sync is
configured, pulls the repo into the ``EXT_STRATEGIES`` staging mount and copies its
``buy``/``sell`` files on top. The app only ever scans ``STRATEGIES_ROOT`` — it never
runs code directly out of ``EXT_STRATEGIES`` — see ``src.modules.com.git.deploy_strategies``.

The git-sync portion is a no-op (with a log line) when ``git_sync.enabled`` is false
or no ``repo_url`` is configured. Safe to run without a reachable database (falls
back to ``default.yml``).
"""

from __future__ import annotations

import asyncio
import os

from src.modules.com.git import GitError, sync_and_deploy
from src.modules.configs import ConfigService, load_default_config
from src.modules.db.connection import Database
from src.modules.logger import get_logger
from src.modules.strategy import seed_missing_strategies

_logger = get_logger("scripts.sync_algorithms")

_DEFAULT_CONFIG_PATH = "src/conf/default.yml"
_DEFAULT_STRATEGIES_ROOT = "strategies"
_DEFAULT_EXT_STRATEGIES_ROOT = "ext_strategies"


async def _load_git_config(config_defaults: dict) -> dict:
    """Resolve the ``git_sync`` section, preferring DB (system) overrides when reachable."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return config_defaults.get("git_sync", {})

    db = Database(database_url)
    try:
        async with db.session() as session:
            values = await ConfigService(session, config_defaults).compile_values()
        return values.get("git_sync", {})
    except Exception as exc:  # noqa: BLE001 - DB not ready yet is a skip, not a crash
        _logger.warning("could not read git_sync config from DB, using defaults: %s", exc)
        return config_defaults.get("git_sync", {})
    finally:
        await db.dispose()


async def main() -> None:
    config_defaults = load_default_config(os.environ.get("CONFIG_PATH", _DEFAULT_CONFIG_PATH))
    git_cfg = await _load_git_config(config_defaults)

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

    if not git_cfg.get("enabled") or not git_cfg.get("repo_url"):
        _logger.info("git sync disabled or repo_url not set; skipping")
        return

    try:
        commit, copied = await sync_and_deploy(
            repo_url=git_cfg["repo_url"],
            branch=git_cfg.get("branch", "main"),
            staging_root=ext_strategies_root,
            target_root=strategies_root,
        )
    except (GitError, OSError) as exc:
        _logger.error("git sync failed, continuing startup with existing strategies: %s", exc)
        return

    _logger.info("startup git sync complete at %s (%d file(s) updated)", commit[:8], len(copied))


if __name__ == "__main__":
    asyncio.run(main())
