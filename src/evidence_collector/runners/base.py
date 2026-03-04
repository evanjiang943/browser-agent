"""Base runner interface for all playbooks."""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any

from evidence_collector.evidence.naming import generate_sample_id
from evidence_collector.io.paths import read_notes


class BaseRunner(abc.ABC):
    """Abstract base class for playbook runners."""

    def __init__(self, input_path: Path, output_dir: Path, config: Any) -> None:
        self.input_path = input_path
        self.output_dir = output_dir
        self.config = config

    @property
    @abc.abstractmethod
    def playbook_name(self) -> str:
        """Return the playbook slug used in directory paths."""
        ...

    @abc.abstractmethod
    def load_samples(self) -> list[dict]:
        """Load and validate input samples from CSV/XLSX."""
        ...

    @abc.abstractmethod
    def process_sample(self, sample: dict) -> dict:
        """Process a single sample: navigate, screenshot, extract, write evidence."""
        ...

    def run(self) -> None:
        """Run the full playbook across all samples."""
        raise NotImplementedError

    def should_skip(self, sample: dict) -> bool:
        """Check if sample is already completed (for resumability)."""
        sample_id = generate_sample_id(
            primary_key=sample.get("primary_key"),
            url=sample.get("url"),
            name=sample.get("name"),
        )
        sample_dir = self.output_dir / "evidence" / self.playbook_name / sample_id
        notes = read_notes(sample_dir)
        return notes is not None and notes.get("status") == "success"
