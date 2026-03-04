"""Tests for utils/time.py."""

import re
from datetime import datetime, timedelta, timezone

from evidence_collector.utils.time import (
    is_within_window,
    now_filename_stamp,
    now_iso,
)


class TestNowIso:
    def test_returns_parseable_iso(self):
        result = now_iso()
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    def test_is_utc(self):
        result = now_iso()
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo == timezone.utc

    def test_is_recent(self):
        result = now_iso()
        dt = datetime.fromisoformat(result)
        assert abs((datetime.now(timezone.utc) - dt).total_seconds()) < 2


class TestNowFilenameStamp:
    def test_format(self):
        result = now_filename_stamp()
        assert re.fullmatch(r"\d{8}-\d{6}", result)


class TestIsWithinWindow:
    def test_recent_date_returns_true(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assert is_within_window(yesterday, 7) is True

    def test_old_date_returns_false(self):
        old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        assert is_within_window(old, 30) is False

    def test_boundary_exact(self):
        boundary = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        # Should not raise; result is a bool
        result = is_within_window(boundary, 30)
        assert isinstance(result, bool)

    def test_naive_datetime_treated_as_utc(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1))
        naive_str = yesterday.replace(tzinfo=None).isoformat()
        assert is_within_window(naive_str, 7) is True

    def test_future_date_returns_true(self):
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        assert is_within_window(future, 1) is True
