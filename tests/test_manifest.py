"""Tests for manifest and logging."""

import json

from evidence_collector.evidence.manifest import RunManifest, SampleNotes, write_manifest
from evidence_collector.evidence.logging import RunLogger
from evidence_collector.io.paths import (
    setup_run_dir,
    setup_sample_dir,
    read_notes,
    write_notes,
)


def test_manifest_roundtrip(tmp_path):
    """Create RunManifest, write it, read back JSON, assert fields match."""
    manifest = RunManifest(
        run_id="run-001",
        playbook="test_playbook",
        input_file="input.csv",
        output_dir=str(tmp_path),
        config={"key": "value"},
        started_at="2025-01-01T00:00:00Z",
        versions={"tool": "1.0"},
    )
    write_manifest(manifest, tmp_path)

    data = json.loads((tmp_path / "run_manifest.json").read_text())
    assert data["run_id"] == "run-001"
    assert data["playbook"] == "test_playbook"
    assert data["input_file"] == "input.csv"
    assert data["config"] == {"key": "value"}
    assert data["started_at"] == "2025-01-01T00:00:00Z"
    assert data["finished_at"] is None
    assert data["versions"] == {"tool": "1.0"}


def test_log_writes_jsonl(tmp_path):
    """RunLogger.log() should append valid JSONL with expected fields."""
    logger = RunLogger(tmp_path)
    logger.log("step_start", sample_id="s1", step="login")
    logger.log("step_end", level="DEBUG", sample_id="s1", step="login")
    logger.log("error", level="ERROR", sample_id="s2", message="timeout")

    lines = (tmp_path / "run_log.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3

    for line in lines:
        entry = json.loads(line)
        assert "timestamp" in entry
        assert "event" in entry
        assert "level" in entry

    first = json.loads(lines[0])
    assert first["event"] == "step_start"
    assert first["sample_id"] == "s1"
    assert first["step"] == "login"


def test_summary_counts(tmp_path):
    """summary() should count sample_end events by status."""
    logger = RunLogger(tmp_path)
    logger.log("sample_end", sample_id="s1", status="success")
    logger.log("sample_end", sample_id="s2", status="success")
    logger.log("sample_end", sample_id="s3", status="failed")
    logger.log("sample_end", sample_id="s4", status="partial")
    logger.log("step_start", sample_id="s5")  # not sample_end, should be ignored

    result = logger.summary()
    assert result == {
        "total": 4,
        "succeeded": 2,
        "failed": 1,
        "partial": 1,
        "retried": 0,
    }


def test_notes_roundtrip(tmp_path):
    """Create notes dict, write with write_notes, read back, assert fields match."""
    sample = tmp_path / "sample-1"
    sample.mkdir()

    notes = SampleNotes(
        sample_id="sample-1",
        status="success",
        steps_completed=["login", "search"],
        errors=[],
        screenshots=["shot1.png"],
        downloads=["file.pdf"],
    )
    write_notes(sample, notes.model_dump())
    result = read_notes(sample)

    assert result["sample_id"] == "sample-1"
    assert result["status"] == "success"
    assert result["steps_completed"] == ["login", "search"]
    assert result["errors"] == []
    assert result["screenshots"] == ["shot1.png"]
    assert result["downloads"] == ["file.pdf"]


def test_notes_atomic_write(tmp_path):
    """Verify no .tmp files remain and the file is valid JSON after write."""
    sample = tmp_path / "sample-2"
    sample.mkdir()

    notes = {"sample_id": "sample-2", "status": "pending"}
    write_notes(sample, notes)

    tmp_files = list(sample.glob("*.tmp"))
    assert tmp_files == []

    data = json.loads((sample / "notes.json").read_text())
    assert data["sample_id"] == "sample-2"


def test_read_notes_missing(tmp_path):
    """read_notes returns None when no notes.json exists."""
    assert read_notes(tmp_path) is None


def test_setup_run_dir(tmp_path):
    """Verify directory structure and placeholder files created by setup_run_dir."""
    out = tmp_path / "run-output"
    result = setup_run_dir(out, "my_playbook", "run-123")

    assert result == out
    assert (out / "run_manifest.json").exists()
    assert (out / "run_log.jsonl").exists()
    assert (out / "evidence" / "my_playbook").is_dir()

    manifest = json.loads((out / "run_manifest.json").read_text())
    assert manifest["run_id"] == "run-123"
    assert manifest["playbook"] == "my_playbook"


def test_setup_sample_dir(tmp_path):
    """Verify screenshots/ and downloads/ subdirs created by setup_sample_dir."""
    evidence = tmp_path / "evidence" / "playbook"
    evidence.mkdir(parents=True)

    sample = setup_sample_dir(evidence, "sample-1")
    assert sample == evidence / "sample-1"
    assert (sample / "screenshots").is_dir()
    assert (sample / "downloads").is_dir()
