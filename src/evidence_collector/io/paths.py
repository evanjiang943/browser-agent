"""Path construction utilities for output directory structure."""

from __future__ import annotations

from pathlib import Path


def run_output_dir(base: Path, playbook: str) -> Path:
    """Build the top-level output directory for a run."""
    # TODO: create and return base/evidence/<playbook>/ path
    raise NotImplementedError


def sample_dir(base: Path, playbook: str, sample_id: str) -> Path:
    """Build the per-sample evidence directory."""
    # TODO: create and return base/evidence/<playbook>/<sample_id>/ path
    raise NotImplementedError


def screenshots_dir(sample_path: Path) -> Path:
    """Build the screenshots subdirectory for a sample."""
    # TODO: create and return sample_path/screenshots/ path
    raise NotImplementedError


def downloads_dir(sample_path: Path) -> Path:
    """Build the downloads subdirectory for a sample."""
    # TODO: create and return sample_path/downloads/ path
    raise NotImplementedError


def ensure_dirs(path: Path) -> Path:
    """Create directory and parents if they don't exist."""
    # TODO: mkdir -p equivalent
    raise NotImplementedError
