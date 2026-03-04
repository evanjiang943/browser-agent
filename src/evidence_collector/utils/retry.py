"""Retry logic with exponential backoff."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


async def retry_async(
    fn: Callable,
    max_attempts: int = 3,
    backoff_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
) -> Any:
    """Retry an async function with exponential backoff.

    Calls ``await fn()`` up to *max_attempts* times.  On a retryable
    exception the helper sleeps ``backoff_base ** attempt`` seconds
    (attempt is 1-indexed) before the next try.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except retryable_exceptions:
            if attempt == max_attempts:
                raise
            delay = backoff_base ** attempt
            logger.warning(
                "Attempt %d/%d failed, retrying in %.1fs",
                attempt,
                max_attempts,
                delay,
                exc_info=True,
            )
            await asyncio.sleep(delay)


def retry_sync(
    fn: Callable,
    max_attempts: int = 3,
    backoff_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
) -> Any:
    """Retry a sync function with exponential backoff.

    Same semantics as :func:`retry_async` but uses ``time.sleep``.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except retryable_exceptions:
            if attempt == max_attempts:
                raise
            delay = backoff_base ** attempt
            logger.warning(
                "Attempt %d/%d failed, retrying in %.1fs",
                attempt,
                max_attempts,
                delay,
                exc_info=True,
            )
            time.sleep(delay)
