"""Run manifest creation and management."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def create_manifest(
    output_dir: Path,
    playbook: str,
    input_path: Path,
    config: dict,
    total_samples: int,
) -> dict:
    """Create and write the initial run_manifest.json."""
    # TODO: build manifest dict with inputs, config, versions, start timestamp,
    #       write to output_dir/run_manifest.json
    raise NotImplementedError


def update_manifest(output_dir: Path, updates: dict) -> None:
    """Update an existing run manifest with completion info."""
    # TODO: read existing manifest, merge updates (end time, summary stats),
    #       write back atomically
    raise NotImplementedError


def write_sample_notes(
    sample_dir: Path,
    sample_id: str,
    status: str,
    steps_completed: list[str],
    errors: list[str] | None = None,
    artifacts: dict | None = None,
) -> None:
    """Write per-sample notes.json with status and step tracking."""
    # TODO: build notes dict, write to sample_dir/notes.json
    raise NotImplementedError


def read_sample_notes(sample_dir: Path) -> dict | None:
    """Read existing notes.json for a sample, if it exists."""
    # TODO: read and parse notes.json, return None if not found
    raise NotImplementedError
