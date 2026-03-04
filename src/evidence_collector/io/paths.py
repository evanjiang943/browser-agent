"""Path construction and directory setup for output directory structure."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def setup_run_dir(out_dir: str | Path, playbook: str, run_id: str) -> Path:
    """Create the run output directory with placeholder files.

    Creates:
        out_dir/run_manifest.json  (placeholder with run_id and playbook)
        out_dir/run_log.jsonl      (empty)
        out_dir/evidence/<playbook>/

    Returns the out_dir as a Path.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Placeholder manifest
    manifest_path = out / "run_manifest.json"
    manifest_path.write_text(
        json.dumps({"run_id": run_id, "playbook": playbook}, indent=2)
    )

    # Empty log file
    (out / "run_log.jsonl").touch()

    # Evidence directory for this playbook
    evidence_dir = out / "evidence" / playbook
    evidence_dir.mkdir(parents=True, exist_ok=True)

    return out


def setup_sample_dir(evidence_dir: str | Path, sample_id: str) -> Path:
    """Create per-sample directory with screenshots/ and downloads/ subdirs.

    Returns the sample directory path.
    """
    sample = Path(evidence_dir) / sample_id
    (sample / "screenshots").mkdir(parents=True, exist_ok=True)
    (sample / "downloads").mkdir(parents=True, exist_ok=True)
    return sample


def read_notes(sample_dir: str | Path) -> dict | None:
    """Read notes.json from a sample directory.

    Returns parsed dict, or None if the file does not exist.
    """
    notes_path = Path(sample_dir) / "notes.json"
    if not notes_path.exists():
        return None
    return json.loads(notes_path.read_text())


def write_notes(sample_dir: str | Path, notes: dict) -> None:
    """Atomically write notes dict to sample_dir/notes.json.

    Writes to a temporary file first, then uses os.replace for atomicity.
    """
    dest = Path(sample_dir) / "notes.json"
    fd, tmp_path = tempfile.mkstemp(dir=sample_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(notes, f, indent=2)
        os.replace(tmp_path, dest)
    except BaseException:
        os.unlink(tmp_path)
        raise
