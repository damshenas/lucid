"""Git sync for strategy files.

Pulls a strategy repository into a staging directory (``local_path`` — a mounted
volume, e.g. ``ALGORITHMS_ROOT``) so new ``buy``/``sell`` files appear without manual
upload. The app never runs code directly out of that staging mount: ``deploy_strategies``
copies the discovered files into the real strategies directory (``STRATEGIES_ROOT``)
afterwards. Uses the ``git`` CLI via asyncio subprocess (no extra dependency). The
resulting commit hash is used as the strategy version.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from src.modules.logger import get_logger

REQUIRED_CONFIG = ["repo_url", "local_path"]
OPTIONAL_CONFIG = {"branch": "main"}

_DIRECTIONS = ("buy", "sell")

_logger = get_logger("com.git")


class GitError(Exception):
    pass


class GitSync:
    def __init__(self, repo_url: str, local_path: str, *, branch: str = "main") -> None:
        self._repo_url = repo_url
        self._path = Path(local_path)
        self._branch = branch

    @staticmethod
    def available() -> bool:
        return shutil.which("git") is not None

    async def _run(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise GitError(stderr.decode().strip() or f"git {' '.join(args)} failed")
        return stdout.decode().strip()

    async def sync(self) -> str:
        """Clone or update the repo, then return the HEAD commit hash."""
        if not (self._path / ".git").is_dir():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            await self._run("clone", "--branch", self._branch, self._repo_url, str(self._path))
        else:
            await self._run("-C", str(self._path), "fetch", "--all", "--prune")
            await self._run("-C", str(self._path), "checkout", self._branch)
            await self._run("-C", str(self._path), "reset", "--hard", f"origin/{self._branch}")
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
    *, repo_url: str, branch: str, staging_root: str | Path, target_root: str | Path
) -> tuple[str, list[str]]:
    """Sync the repo into the staging mount, then deploy files into the target dir.

    Returns ``(head_commit, copied_file_paths)``.
    """
    sync = GitSync(repo_url, str(staging_root), branch=branch)
    commit = await sync.sync()
    copied = deploy_strategies(staging_root, target_root)
    return commit, copied


__all__ = [
    "GitError",
    "GitSync",
    "OPTIONAL_CONFIG",
    "REQUIRED_CONFIG",
    "deploy_strategies",
    "sync_and_deploy",
]
