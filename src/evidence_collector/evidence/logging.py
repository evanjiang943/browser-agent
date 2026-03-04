"""Structured JSONL logging for run events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class RunLogger:
    """Append-only JSONL logger for run events."""

    def __init__(self, out_dir: Path) -> None:
        self.log_path = out_dir / "run_log.jsonl"

    def log(self, event: str, level: str = "INFO", sample_id: str | None = None, **kwargs) -> None:
        """Write a timestamped event to the JSONL log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "level": level,
            "sample_id": sample_id,
            **kwargs,
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def summary(self) -> dict:
        """Read the log and produce summary metrics."""
        counts: dict[str, int] = {}
        try:
            with open(self.log_path) as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("event") == "sample_end":
                        status = entry.get("status", "unknown")
                        counts[status] = counts.get(status, 0) + 1
        except FileNotFoundError:
            pass
        total = sum(counts.values())
        return {
            "total": total,
            "succeeded": counts.get("success", 0),
            "failed": counts.get("failed", 0),
            "partial": counts.get("partial", 0),
            "retried": counts.get("retried", 0),
        }
