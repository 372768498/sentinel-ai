"""
Timezone verification utility.
Call verify_timezones() on worker startup to confirm all jobs are in ET.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


def now_et() -> datetime:
    return datetime.now(_ET)


def now_utc() -> datetime:
    return datetime.now(_UTC)


def to_et(dt: datetime) -> datetime:
    """Convert any timezone-aware datetime to ET."""
    return dt.astimezone(_ET)


def is_quiet_time(enabled: bool, start_hour: int, end_hour: int) -> bool:
    """
    Return True if current ET time falls within user's quiet window.
    Handles midnight-crossing windows (e.g., 22:00 – 07:00).
    """
    if not enabled:
        return False
    hour = now_et().hour
    if start_hour > end_hour:          # crosses midnight: e.g. 22 → 7
        return hour >= start_hour or hour < end_hour
    return start_hour <= hour < end_hour


def et_display(dt: datetime | None = None) -> str:
    """Format a datetime (or now) as human-readable ET string for messages."""
    target = (dt or datetime.now(_ET)).astimezone(_ET)
    return target.strftime("%H:%M ET %b %d")


def verify_timezones(scheduler=None) -> None:
    """
    Print timezone diagnostics on startup.
    Pass the APScheduler instance to also print next_run_time for every job.
    """
    utc = now_utc()
    et = now_et()
    local = datetime.now()
    dst_active = et.dst() != timedelta(0)

    print("=" * 64, flush=True)
    print("TIMEZONE CHECK", flush=True)
    print(f"  UTC:          {utc.strftime('%Y-%m-%d %H:%M:%S %Z')}", flush=True)
    print(f"  ET (NYSE):    {et.strftime('%Y-%m-%d %H:%M:%S %Z')}  ← all jobs use this", flush=True)
    print(f"  Server local: {local.strftime('%Y-%m-%d %H:%M:%S')}  (reference only)", flush=True)
    print(f"  DST active:   {dst_active}", flush=True)

    if scheduler is not None:
        print("  Scheduled jobs:", flush=True)
        for job in scheduler.get_jobs():
            nrt = job.next_run_time
            if nrt:
                nrt_et = to_et(nrt)
                print(f"    [{job.id}] next: {nrt_et.strftime('%Y-%m-%d %H:%M %Z')}", flush=True)
            else:
                print(f"    [{job.id}] next: (paused)", flush=True)

    print("=" * 64, flush=True)
