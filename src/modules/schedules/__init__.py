"""Thin APScheduler wrapper.

Registers named jobs with a hard per-task timeout, ``max_instances=1`` and
``coalesce=True``, and tracks last-run status for the admin UI. APScheduler does the
scheduling — this is only a thin config/observability layer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.modules.logger import get_logger

AsyncJob = Callable[[], Awaitable[None]]
_logger = get_logger("schedules")


@dataclass
class JobStatus:
    id: str
    name: str
    last_run: datetime | None = None
    last_status: str | None = None  # "success" | "error" | "timeout"
    last_error: str | None = None


async def run_with_timeout(func: AsyncJob, *, timeout: float) -> tuple[str, str | None]:
    try:
        await asyncio.wait_for(func(), timeout=timeout)
        return "success", None
    except asyncio.TimeoutError:
        return "timeout", f"exceeded {timeout}s"
    except Exception as exc:  # noqa: BLE001 - report any job failure as status
        return "error", str(exc)


class Scheduler:
    def __init__(self, *, timeout_seconds: float = 300.0) -> None:
        self._scheduler = AsyncIOScheduler()
        self._timeout = timeout_seconds
        self._status: dict[str, JobStatus] = {}
        self._runners: dict[str, AsyncJob] = {}

    def _make_runner(self, func: AsyncJob, job_id: str, name: str) -> AsyncJob:
        async def runner() -> None:
            status, error = await run_with_timeout(func, timeout=self._timeout)
            self._status[job_id] = JobStatus(
                id=job_id,
                name=name,
                last_run=datetime.now(timezone.utc),
                last_status=status,
                last_error=error,
            )
            if status != "success":
                _logger.error("job %s finished with status=%s: %s", job_id, status, error)

        return runner

    def add_job(
        self,
        func: AsyncJob,
        *,
        id: str,
        trigger,
        name: str | None = None,
    ) -> None:
        name = name or id
        runner = self._make_runner(func, id, name)
        self._runners[id] = runner
        self._status[id] = JobStatus(id=id, name=name)
        self._scheduler.add_job(
            runner,
            trigger=trigger,
            id=id,
            name=name,
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )

    def add_interval_job(self, func: AsyncJob, *, id: str, name: str | None = None, **interval) -> None:
        self.add_job(func, id=id, name=name, trigger=IntervalTrigger(**interval))

    def add_cron_job(self, func: AsyncJob, *, id: str, name: str | None = None, **cron) -> None:
        self.add_job(func, id=id, name=name, trigger=CronTrigger(**cron))

    async def trigger_job(self, job_id: str) -> JobStatus:
        """Run a registered job now (used for manual runs and tests)."""
        runner = self._runners.get(job_id)
        if runner is None:
            raise KeyError(f"no job '{job_id}'")
        await runner()
        return self._status[job_id]

    def job_list(self) -> list[JobStatus]:
        return list(self._status.values())

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self, *, wait: bool = False) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)


__all__ = ["JobStatus", "Scheduler", "run_with_timeout"]
