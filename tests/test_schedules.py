"""M9: scheduler timeout enforcement, status tracking, and job registration."""

from __future__ import annotations

import asyncio

from src.modules.schedules import Scheduler, run_with_timeout


async def test_run_with_timeout_success() -> None:
    async def ok() -> None:
        return None

    assert await run_with_timeout(ok, timeout=1) == ("success", None)


async def test_run_with_timeout_times_out() -> None:
    async def slow() -> None:
        await asyncio.sleep(1)

    status, error = await run_with_timeout(slow, timeout=0.01)
    assert status == "timeout"
    assert "0.01" in (error or "")


async def test_run_with_timeout_error() -> None:
    async def boom() -> None:
        raise ValueError("nope")

    status, error = await run_with_timeout(boom, timeout=1)
    assert status == "error"
    assert error == "nope"


async def test_scheduler_tracks_status_and_registers() -> None:
    scheduler = Scheduler(timeout_seconds=1)
    ran = {"n": 0}

    async def job() -> None:
        ran["n"] += 1

    scheduler.add_interval_job(job, id="poll", name="Poll", seconds=30)

    # registered with coalesce + single instance
    apscheduler_job = scheduler._scheduler.get_job("poll")
    assert apscheduler_job is not None
    assert apscheduler_job.max_instances == 1
    assert apscheduler_job.coalesce is True

    status = await scheduler.trigger_job("poll")
    assert ran["n"] == 1
    assert status.last_status == "success"
    assert status.last_run is not None

    listing = scheduler.job_list()
    assert any(j.id == "poll" for j in listing)


async def test_scheduler_records_timeout_status() -> None:
    scheduler = Scheduler(timeout_seconds=0.01)

    async def slow() -> None:
        await asyncio.sleep(1)

    scheduler.add_interval_job(slow, id="slow", seconds=30)
    status = await scheduler.trigger_job("slow")
    assert status.last_status == "timeout"
