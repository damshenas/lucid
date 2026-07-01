"""Git sync for strategy files.

Pulls a strategy repository into ``local_path`` so new ``strategies/buy`` and
``strategies/sell`` files appear without manual upload. Uses the ``git`` CLI via
asyncio subprocess (no extra dependency). The resulting commit hash is used as the
strategy version.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from src.modules.logger import get_logger

REQUIRED_CONFIG = ["repo_url", "local_path"]
OPTIONAL_CONFIG = {"branch": "main"}

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


__all__ = ["GitError", "GitSync", "OPTIONAL_CONFIG", "REQUIRED_CONFIG"]
