"""Retry logic with exponential backoff."""

from __future__ import annotations

from typing import Any, Callable


async def retry_async(
    fn: Callable,
    max_attempts: int = 3,
    backoff_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
) -> Any:
    """Retry an async function with exponential backoff."""
    # TODO: call fn, on retryable exception sleep backoff_base^attempt and retry,
    #       raise after max_attempts exhausted
    raise NotImplementedError


def retry_sync(
    fn: Callable,
    max_attempts: int = 3,
    backoff_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
) -> Any:
    """Retry a sync function with exponential backoff."""
    # TODO: same as retry_async but synchronous
    raise NotImplementedError
