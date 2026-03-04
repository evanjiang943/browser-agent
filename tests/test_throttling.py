"""Tests for evidence_collector.utils.throttling."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from evidence_collector.utils.throttling import CircuitBreaker, Throttle


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttle_under_limit():
    """acquire() should not sleep when under the rate limit."""
    throttle = Throttle(max_per_minute=5)
    with patch("evidence_collector.utils.throttling.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        for _ in range(5):
            await throttle.acquire()
    mock_sleep.assert_not_awaited()
    assert len(throttle._timestamps) == 5


@pytest.mark.asyncio
async def test_throttle_at_limit_sleeps():
    """acquire() should sleep when rate limit is reached."""
    throttle = Throttle(max_per_minute=2)
    # Pre-fill with recent timestamps
    now = time.monotonic()
    throttle._timestamps = [now, now + 0.01]

    with patch("evidence_collector.utils.throttling.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # Next acquire should see the window is full and sleep
        await throttle.acquire()

    assert mock_sleep.await_count >= 1


def test_throttle_reset():
    throttle = Throttle(max_per_minute=5)
    throttle._timestamps = [time.monotonic()] * 5
    throttle.reset()
    assert throttle._timestamps == []


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker(failure_threshold=3)
    assert not cb.is_open()


def test_circuit_breaker_opens_at_threshold():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert not cb.is_open()
    cb.record_failure()
    assert cb.is_open()


def test_circuit_breaker_resets_on_success():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert not cb.is_open()
    # Need 3 more consecutive failures to open again
    cb.record_failure()
    assert not cb.is_open()


def test_circuit_breaker_stays_open_past_threshold():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()  # past threshold
    assert cb.is_open()
