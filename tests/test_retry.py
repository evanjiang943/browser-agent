"""Tests for evidence_collector.utils.retry."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evidence_collector.utils.retry import retry_async, retry_sync


# ---------------------------------------------------------------------------
# retry_async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_async_succeeds_first_try():
    fn = AsyncMock(return_value="ok")
    result = await retry_async(fn)
    assert result == "ok"
    assert fn.await_count == 1


@pytest.mark.asyncio
async def test_retry_async_succeeds_after_failures():
    fn = AsyncMock(side_effect=[ValueError("boom"), ValueError("boom"), "ok"])
    with patch("evidence_collector.utils.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await retry_async(fn, max_attempts=3)
    assert result == "ok"
    assert fn.await_count == 3
    # Backoff: 2^1=2, 2^2=4
    mock_sleep.assert_any_call(2.0)
    mock_sleep.assert_any_call(4.0)
    assert mock_sleep.await_count == 2


@pytest.mark.asyncio
async def test_retry_async_raises_after_exhaustion():
    fn = AsyncMock(side_effect=ValueError("boom"))
    with patch("evidence_collector.utils.retry.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ValueError, match="boom"):
            await retry_async(fn, max_attempts=3)
    assert fn.await_count == 3


@pytest.mark.asyncio
async def test_retry_async_non_retryable_propagates():
    """Exceptions not in retryable_exceptions propagate immediately."""
    fn = AsyncMock(side_effect=TypeError("wrong type"))
    with pytest.raises(TypeError, match="wrong type"):
        await retry_async(fn, max_attempts=3, retryable_exceptions=(ValueError,))
    assert fn.await_count == 1


@pytest.mark.asyncio
async def test_retry_async_custom_backoff():
    fn = AsyncMock(side_effect=[RuntimeError(), "done"])
    with patch("evidence_collector.utils.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await retry_async(fn, max_attempts=2, backoff_base=3.0)
    assert result == "done"
    mock_sleep.assert_awaited_once_with(3.0)  # 3^1


# ---------------------------------------------------------------------------
# retry_sync
# ---------------------------------------------------------------------------


def test_retry_sync_succeeds_first_try():
    fn = MagicMock(return_value="ok")
    result = retry_sync(fn)
    assert result == "ok"
    assert fn.call_count == 1


def test_retry_sync_succeeds_after_failures():
    fn = MagicMock(side_effect=[ValueError("boom"), ValueError("boom"), "ok"])
    with patch("evidence_collector.utils.retry.time.sleep") as mock_sleep:
        result = retry_sync(fn, max_attempts=3)
    assert result == "ok"
    assert fn.call_count == 3
    mock_sleep.assert_any_call(2.0)
    mock_sleep.assert_any_call(4.0)
    assert mock_sleep.call_count == 2


def test_retry_sync_raises_after_exhaustion():
    fn = MagicMock(side_effect=ValueError("boom"))
    with patch("evidence_collector.utils.retry.time.sleep"):
        with pytest.raises(ValueError, match="boom"):
            retry_sync(fn, max_attempts=3)
    assert fn.call_count == 3


def test_retry_sync_non_retryable_propagates():
    fn = MagicMock(side_effect=TypeError("wrong type"))
    with pytest.raises(TypeError, match="wrong type"):
        retry_sync(fn, max_attempts=3, retryable_exceptions=(ValueError,))
    assert fn.call_count == 1
