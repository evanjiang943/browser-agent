"""Tests for evidence_collector.utils.throttling."""

from __future__ import annotations

import asyncio
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


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttle_expired_timestamps_pruned():
    """Timestamps older than 60s are pruned; acquire() doesn't sleep."""
    throttle = Throttle(max_per_minute=2)
    # Pre-fill with timestamps from 70 seconds ago (expired)
    old = time.monotonic() - 70.0
    throttle._timestamps = [old, old + 0.01]

    with patch("evidence_collector.utils.throttling.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await throttle.acquire()
    mock_sleep.assert_not_awaited()
    # Only the new timestamp should remain (old ones pruned)
    assert len(throttle._timestamps) == 1


@pytest.mark.asyncio
async def test_throttle_concurrent_acquire_respects_lock():
    """Two concurrent tasks with limit=1: second must wait for the first's slot to expire."""
    throttle = Throttle(max_per_minute=1)
    order = []

    real_sleep = asyncio.sleep

    async def fake_sleep(duration):
        # Simulate time passing by clearing timestamps
        throttle._timestamps.clear()
        await real_sleep(0)

    with patch("evidence_collector.utils.throttling.asyncio.sleep", side_effect=fake_sleep):
        async def task(label):
            await throttle.acquire()
            order.append(label)

        # Both tasks compete for the single slot
        await asyncio.gather(task("a"), task("b"))

    assert len(order) == 2
    # Both completed, and lock ensured sequential access
    assert set(order) == {"a", "b"}


def test_circuit_breaker_pause_seconds_auto_resets():
    """After pause_seconds elapse, is_open() returns False (auto-reset)."""
    cb = CircuitBreaker(failure_threshold=2, pause_seconds=0.05)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open()

    # Simulate time passing by backdating _opened_at
    cb._opened_at = time.monotonic() - 0.1

    assert not cb.is_open()
    assert cb._consecutive_failures == 0


def test_circuit_breaker_threshold_one():
    """threshold=1: opens on first failure."""
    cb = CircuitBreaker(failure_threshold=1)
    assert not cb.is_open()
    cb.record_failure()
    assert cb.is_open()


def test_circuit_breaker_opened_at_cleared_on_success():
    """record_success() clears _opened_at."""
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open()
    assert cb._opened_at is not None

    cb.record_success()
    assert cb._opened_at is None
    assert not cb.is_open()
