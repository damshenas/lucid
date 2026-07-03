"""Git sync for strategy files.

``local_path`` (``EXT_STRATEGIES``, a mounted volume) is expected to already be a git
checkout — set up out-of-band on the host with the desired remote/branch — so all this
does is run ``git pull`` in it on demand (triggered by an admin, not on a schedule) so
new ``buy``/``sell`` files appear without manual upload. The app never runs code
directly out of that staging mount: ``deploy_strategies`` copies the discovered files
into the real strategies directory (``STRATEGIES_ROOT``) afterwards. Uses the ``git``
CLI via asyncio subprocess (no extra dependency). The resulting commit hash is used as
the strategy version.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from src.modules.logger import get_logger

REQUIRED_CONFIG = ["local_path"]

_DIRECTIONS = ("buy", "sell")

_logger = get_logger("com.git")


class GitError(Exception):
    pass


class GitSync:
    def __init__(self, local_path: str) -> None:
        self._path = Path(local_path)

    @staticmethod
    def available() -> bool:
        return shutil.which("git") is not None

    async def _run(self, *args: str) -> str:
        # EXT_STRATEGIES is a bind-mounted volume typically owned by a different
        # uid/gid than the container's non-root runtime user (docker/Dockerfile), so
        # git's ownership check (>= 2.35.2) refuses to operate on it as "dubious
        # ownership" unless explicitly told it's safe. Passed per-invocation (not
        # written to a global ~/.gitconfig) since the container filesystem is
        # read-only (docker/compose.yml) besides the /data and /ext_strategies mounts.
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            f"safe.directory={self._path}",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            message = stderr.decode().strip() or f"git {' '.join(args)} failed"
            if "permission denied" in message.lower():
                # The checkout's files (e.g. .git/FETCH_HEAD, written on every pull)
                # are owned by whatever host user ran `git clone`, not necessarily the
                # container's non-root uid/gid (see docker/Dockerfile) — fix with
                # `sudo bash docker/prepare.sh` (chowns EXT_STRATEGIES recursively too,
                # see docs/deployment.md), re-run after (re)cloning.
                message += (
                    f" — {self._path} (or files inside it, e.g. .git/FETCH_HEAD) "
                    "isn't owned/writable by the container's runtime user; re-run "
                    "`sudo bash docker/prepare.sh` on the host after cloning/updating "
                    "it out-of-band"
                )
            raise GitError(message)
        return stdout.decode().strip()

    async def sync(self) -> str:
        """Pull the already-cloned repo, then return the HEAD commit hash.

        Does not clone: ``local_path`` must already be a git checkout with its
        remote/branch configured (set up manually on the host), matching how
        ``EXT_STRATEGIES`` is provisioned.
        """
        if not (self._path / ".git").is_dir():
            raise GitError(
                f"{self._path} is not a git checkout (no .git directory) — clone it "
                "on the host with the desired remote/branch first"
            )
        await self._run("-C", str(self._path), "pull")
        commit = await self.head_commit()
        _logger.info("strategy repo synced to %s", commit[:8])
        return commit

    async def head_commit(self) -> str:
        return await self._run("-C", str(self._path), "rev-parse", "HEAD")


def deploy_strategies(staging_root: str | Path, target_root: str | Path) -> list[str]:
    """Copy discovered ``buy``/``sell`` strategy files from the staging mount into the
    directory the app actually loads strategies from.

    Never deletes files in ``target_root`` — built-in strategies shipped with the image
    are left untouched; the staged repo only ever adds or updates files.
    """
    staging = Path(staging_root)
    target = Path(target_root)
    copied: list[str] = []
    for direction in _DIRECTIONS:
        src_dir = staging / direction
        if not src_dir.is_dir():
            continue
        dst_dir = target / direction
        dst_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(src_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            shutil.copy2(path, dst_dir / path.name)
            copied.append(f"{direction}/{path.name}")
    if copied:
        _logger.info("deployed %d strategy file(s) from %s to %s", len(copied), staging, target)
    return copied


async def sync_and_deploy(
    *, staging_root: str | Path, target_root: str | Path
) -> tuple[str, list[str]]:
    """Pull the already-cloned staging repo, then deploy files into the target dir.

    Returns ``(head_commit, copied_file_paths)``.
    """
    sync = GitSync(str(staging_root))
    commit = await sync.sync()
    copied = deploy_strategies(staging_root, target_root)
    return commit, copied


__all__ = [
    "GitError",
    "GitSync",
    "REQUIRED_CONFIG",
    "deploy_strategies",
    "sync_and_deploy",
]
