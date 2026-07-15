"""M9: scheduler timeout enforcement, status tracking, and job registration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from src.modules.schedules import Scheduler, run_with_timeout
from src.modules.schedules import market_hours


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


def test_market_hours_us_open_during_session() -> None:
    # Wednesday 2026-07-15 15:00 UTC == 11:00 America/New_York (EDT, UTC-4) — well
    # within the 09:30-16:00 US session.
    moment = datetime(2026, 7, 15, 15, 0, tzinfo=timezone.utc)
    assert market_hours.is_open(market_hours.US, moment) is True


def test_market_hours_us_closed_outside_session() -> None:
    # Same Wednesday, 02:00 UTC == 22:00 the prior day America/New_York — market closed.
    moment = datetime(2026, 7, 15, 2, 0, tzinfo=timezone.utc)
    assert market_hours.is_open(market_hours.US, moment) is False


def test_market_hours_closed_on_weekend() -> None:
    # Saturday 2026-07-18, mid-session UTC time — markets are closed regardless.
    moment = datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc)
    assert market_hours.is_open(market_hours.US, moment) is False
    assert market_hours.is_open(market_hours.EU, moment) is False
    assert market_hours.is_open(market_hours.EM, moment) is False


def test_market_hours_eu_and_em_sessions() -> None:
    # Wednesday 2026-07-15 10:00 UTC == 11:00 Europe/London (BST, UTC+1) — within
    # the 08:00-16:30 EU session.
    eu_moment = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
    assert market_hours.is_open(market_hours.EU, eu_moment) is True

    # Wednesday 2026-07-15 03:00 UTC == 11:00 Asia/Shanghai (UTC+8) — within the
    # 09:30-15:00 EM session.
    em_moment = datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)
    assert market_hours.is_open(market_hours.EM, em_moment) is True


def test_market_hours_unknown_region_defaults_open() -> None:
    moment = datetime(2026, 7, 18, 3, 0, tzinfo=timezone.utc)  # a Saturday
    assert market_hours.is_open("apac", moment) is True
