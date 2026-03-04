"""Run manifest creation and management."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel


from typing import Literal


class SampleNotes(BaseModel):
    sample_id: str
    status: Literal["pending", "success", "failed", "partial"]
    steps_completed: list[str] = []
    errors: list[str] = []
    screenshots: list[str] = []
    downloads: list[str] = []


class RunManifest(BaseModel):
    run_id: str
    playbook: str
    input_file: str
    output_dir: str
    config: dict
    started_at: str
    finished_at: str | None = None
    versions: dict = {}


def write_manifest(manifest: RunManifest, out_dir: Path) -> None:
    """Serialize manifest to JSON and write atomically to out_dir/run_manifest.json."""
    dest = out_dir / "run_manifest.json"
    fd, tmp_path = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(manifest.model_dump_json(indent=2))
        os.replace(tmp_path, dest)
    except BaseException:
        os.unlink(tmp_path)
        raise
