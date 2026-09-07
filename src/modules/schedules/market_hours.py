"""Simplified per-region market-hours gating (US/EU/EM equity sessions).

Not a full holiday-aware exchange calendar — just a weekday + local-time-window
check using the stdlib ``zoneinfo`` (no new dependency). Good enough to stop
intraday price-fetch jobs and strategy evaluation from running against a market
that's currently closed; a real holiday calendar can be layered in later if needed.

Used by ``TradingRuntime`` (see src/api/runtime.py) — gated by the
``schedule.market_hours_enabled`` config flag, which defaults on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

US = "us"
EU = "eu"
EM = "em"

REGIONS = (US, EU, EM)


@dataclass(frozen=True)
class RegionHours:
    timezone: str
    open_time: time
    close_time: time


# Standard equity-session hours per region, in each region's own local time.
REGION_HOURS: dict[str, RegionHours] = {
    US: RegionHours("America/New_York", time(9, 30), time(16, 0)),
    EU: RegionHours("Europe/London", time(8, 0), time(16, 30)),
    EM: RegionHours("Asia/Shanghai", time(9, 30), time(15, 0)),
}


def is_open(region: str, now: datetime | None = None) -> bool:
    """Whether ``region``'s equity market is open at ``now`` (defaults to the
    current UTC time). Monday-Friday only, within the region's local open/close
    window. An unrecognized region always reports open (fail open, never silently
    stop fetching/evaluating a ticker just because its region tag is unknown)."""
    hours = REGION_HOURS.get(region)
    if hours is None:
        return True
    moment = now or datetime.now(timezone.utc)
    local = moment.astimezone(ZoneInfo(hours.timezone))
    if local.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    # Close boundary is exclusive — at the exact close instant the session has
    # already ended, not "still open for one more instant" (bugs.md finding 16).
    return hours.open_time <= local.time() < hours.close_time


__all__ = ["EM", "EU", "REGIONS", "REGION_HOURS", "US", "RegionHours", "is_open"]
