"""Time and date utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def now_filename_stamp() -> str:
    """Return current time formatted for filenames: YYYYMMDD-HHMMSS."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def is_within_window(date_str: str, window_days: int) -> bool:
    """Check if a date string falls within the last N days.

    Naive datetimes are treated as UTC.
    """
    dt = datetime.fromisoformat(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    return dt >= cutoff
