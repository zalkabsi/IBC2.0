"""IBKR's forced weekly re-authentication, and the nightly restart time.

IBKR requires a fresh, fully authenticated login (including second factor)
the first time TWS/Gateway runs after 01:00 New York time on Sunday. Nothing
can avoid that, but we can tell you in advance so the approval happens while
you are awake.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def next_weekly_reauth(now: datetime | None = None) -> datetime:
    """The next Sunday 01:00 New York time strictly after *now* (tz-aware)."""
    now = (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)
    days_ahead = (6 - now.weekday()) % 7  # Monday=0 ... Sunday=6
    candidate = (now + timedelta(days=days_ahead)).replace(hour=1, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def default_auto_restart_time(now: datetime | None = None) -> str:
    """01:30 New York time expressed as a local 12-hour clock string, e.g. ``"01:30 AM"``.

    TWS/Gateway interpret the auto-restart time in the machine's local time zone.
    Picking a fixed local time (e.g. 11:45 PM, the TWS default) can land in the
    middle of US trading hours for users in other time zones.
    """
    now = now if now is not None else datetime.now().astimezone()
    ny = now.astimezone(NEW_YORK).replace(hour=1, minute=30, second=0, microsecond=0)
    local = ny.astimezone(now.tzinfo)
    return local.strftime("%I:%M %p")


def format_local(dt: datetime) -> str:
    return dt.astimezone().strftime("%a %Y-%m-%d %H:%M %Z")
