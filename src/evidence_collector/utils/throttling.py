"""Rate limiting and throttling."""

from __future__ import annotations

import asyncio
import time


class Throttle:
    """Sliding-window rate limiter (max N requests per 60-second window)."""

    def __init__(self, max_per_minute: int = 20) -> None:
        self.max_per_minute = max_per_minute
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request slot is available, then record the request."""
        async with self._lock:
            while True:
                now = time.monotonic()
                # Prune timestamps older than 60s
                self._timestamps = [
                    ts for ts in self._timestamps if now - ts < 60.0
                ]
                if len(self._timestamps) < self.max_per_minute:
                    break
                # Sleep until the oldest timestamp expires
                sleep_for = 60.0 - (now - self._timestamps[0])
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)

            self._timestamps.append(time.monotonic())

    def reset(self) -> None:
        """Clear all recorded timestamps."""
        self._timestamps.clear()


class CircuitBreaker:
    """Circuit breaker that opens after repeated consecutive failures.

    After *failure_threshold* consecutive failures the breaker opens.
    It auto-resets (half-open → closed) once *pause_seconds* have elapsed,
    allowing the next call through.
    """

    def __init__(
        self, failure_threshold: int = 5, pause_seconds: float = 60.0
    ) -> None:
        self.failure_threshold = failure_threshold
        self.pause_seconds = pause_seconds
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    def record_success(self) -> None:
        """Reset the failure counter on a successful operation."""
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        """Increment the consecutive failure counter."""
        self._consecutive_failures += 1
        if (
            self._consecutive_failures >= self.failure_threshold
            and self._opened_at is None
        ):
            self._opened_at = time.monotonic()

    def is_open(self) -> bool:
        """Return True if the breaker is open and pause has not elapsed."""
        if self._consecutive_failures < self.failure_threshold:
            return False
        # Auto-reset after pause_seconds
        if (
            self._opened_at is not None
            and time.monotonic() - self._opened_at >= self.pause_seconds
        ):
            self._consecutive_failures = 0
            self._opened_at = None
            return False
        return True
