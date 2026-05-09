"""
NYSE trading day checks using pandas_market_calendars.
Falls back to simple Mon-Fri check if the library is unavailable.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

try:
    import pandas_market_calendars as mcal  # type: ignore
    _NYSE = mcal.get_calendar("NYSE")
    _HAS_MCal = True
except Exception:
    _HAS_MCal = False
    logger.warning("pandas_market_calendars not available — using simple Mon-Fri check")


def is_trading_day(dt: date | None = None) -> bool:
    """Return True if `dt` (default: today ET) is a NYSE trading day."""
    check = dt or date.today()
    if not _HAS_MCal:
        return check.weekday() < 5  # Mon=0 … Fri=4

    try:
        schedule = _NYSE.schedule(
            start_date=check.strftime("%Y-%m-%d"),
            end_date=check.strftime("%Y-%m-%d"),
        )
        return not schedule.empty
    except Exception as exc:
        logger.warning("mcal schedule check failed: %s — falling back", exc)
        return check.weekday() < 5


def today_et() -> date:
    """Return today's date in US Eastern time."""
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        return datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return date.today()
