"""Base runner interface for all playbooks."""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any


class BaseRunner(abc.ABC):
    """Abstract base class for playbook runners."""

    def __init__(self, input_path: Path, output_dir: Path, config: Any) -> None:
        self.input_path = input_path
        self.output_dir = output_dir
        self.config = config

    @abc.abstractmethod
    def load_samples(self) -> list[dict]:
        """Load and validate input samples from CSV/XLSX."""
        # TODO: read input file, validate required columns, return sample dicts
        ...

    @abc.abstractmethod
    def process_sample(self, sample: dict) -> dict:
        """Process a single sample: navigate, screenshot, extract, write evidence."""
        # TODO: implement per-playbook sample processing
        ...

    def run(self) -> None:
        """Run the full playbook across all samples."""
        # TODO: load samples, iterate with throttle/retry, write results CSV + manifest
        raise NotImplementedError

    def should_skip(self, sample: dict) -> bool:
        """Check if sample is already completed (for resumability)."""
        # TODO: check notes.json status for this sample
        raise NotImplementedError
