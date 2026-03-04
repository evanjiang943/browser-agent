"""Structured JSONL logging for run events."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class RunLogger:
    """Append-only JSONL logger for run events."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path

    def log(self, event: str, data: dict | None = None) -> None:
        """Write a timestamped event to the JSONL log."""
        # TODO: build log entry with timestamp + event + data, append to file
        raise NotImplementedError

    def log_sample_start(self, sample_id: str) -> None:
        """Log the start of processing a sample."""
        # TODO: log event="sample_start" with sample_id
        raise NotImplementedError

    def log_sample_end(self, sample_id: str, status: str, error: str | None = None) -> None:
        """Log the completion of a sample."""
        # TODO: log event="sample_end" with sample_id, status, error
        raise NotImplementedError

    def log_step(self, sample_id: str, step: str, status: str) -> None:
        """Log completion of an individual step within a sample."""
        # TODO: log event="step_complete" with sample_id, step, status
        raise NotImplementedError

    def summary(self) -> dict:
        """Read the log and produce summary metrics."""
        # TODO: count total/succeeded/failed/partial/retries from log entries
        raise NotImplementedError
