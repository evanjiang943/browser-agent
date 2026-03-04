"""Tests for manifest and logging."""

import json

from evidence_collector.evidence.manifest import RunManifest, write_manifest
from evidence_collector.evidence.logging import RunLogger


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
    logger.log("sample_end", sample_id="s1", status="succeeded")
    logger.log("sample_end", sample_id="s2", status="succeeded")
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
