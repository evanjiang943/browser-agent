"""Tests for CLI commands."""

import json

from typer.testing import CliRunner

from evidence_collector.cli import app

runner = CliRunner()


def test_run_help():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "playbook" in result.output.lower()


def test_run_creates_output(tmp_path):
    csv_file = tmp_path / "input.csv"
    csv_file.write_text("url\nhttps://example.com\n")
    out_dir = tmp_path / "output"

    result = runner.invoke(app, ["run", "tickets", "--input", str(csv_file), "--out", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert "starting" in result.output

    manifest_path = out_dir / "run_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["finished_at"] is not None
    assert manifest["playbook"] == "tickets"


def test_run_invalid_playbook(tmp_path):
    csv_file = tmp_path / "input.csv"
    csv_file.write_text("url\nhttps://example.com\n")

    result = runner.invoke(app, ["run", "bogus", "--input", str(csv_file)])
    assert result.exit_code != 0


def test_validate_valid(tmp_path):
    csv_file = tmp_path / "input.csv"
    csv_file.write_text("url,summary\nhttps://example.com,test\n")

    result = runner.invoke(app, ["validate", "--playbook", "tickets", "--input", str(csv_file)])
    assert result.exit_code == 0
    assert "Rows: 1" in result.output


def test_validate_missing_columns(tmp_path):
    csv_file = tmp_path / "input.csv"
    csv_file.write_text("summary\ntest\n")

    result = runner.invoke(app, ["validate", "--playbook", "tickets", "--input", str(csv_file)])
    assert result.exit_code == 1
    assert "url" in result.output


def test_resume_no_manifest(tmp_path):
    result = runner.invoke(app, ["resume", "--run-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "run_manifest.json" in result.output
