"""Rate limiting and throttling."""

from __future__ import annotations

import asyncio
import time


class Throttle:
    """Sliding-window rate limiter (max N requests per 60-second window)."""

    def __init__(self, max_per_minute: int = 20) -> None:
        self.max_per_minute = max_per_minute
        self._timestamps: list[float] = []

    async def acquire(self) -> None:
        """Wait until a request slot is available, then record the request."""
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
    """Circuit breaker that opens after repeated consecutive failures."""

    def __init__(
        self, failure_threshold: int = 5, pause_seconds: float = 60.0
    ) -> None:
        self.failure_threshold = failure_threshold
        self.pause_seconds = pause_seconds
        self._consecutive_failures = 0

    def record_success(self) -> None:
        """Reset the failure counter on a successful operation."""
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Increment the consecutive failure counter."""
        self._consecutive_failures += 1

    def is_open(self) -> bool:
        """Return True if consecutive failures have reached the threshold."""
        return self._consecutive_failures >= self.failure_threshold
