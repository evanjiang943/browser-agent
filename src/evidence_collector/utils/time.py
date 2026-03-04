"""Time and date utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    # TODO: return datetime.utcnow().isoformat()
    raise NotImplementedError


def now_filename_stamp() -> str:
    """Return current time formatted for filenames: YYYYMMDD-HHMMSS."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def is_within_window(date_str: str, window_days: int) -> bool:
    """Check if a date string falls within the last N days."""
    # TODO: parse date_str, compare to now, return bool
    raise NotImplementedError
