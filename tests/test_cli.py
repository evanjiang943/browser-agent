"""Tests for CLI commands."""

import json

from typer.testing import CliRunner

from evidence_collector.cli import app

runner = CliRunner()


def test_run_help():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "task" in result.output.lower() or "describe" in result.output.lower()


def test_run_requires_task_or_describe(tmp_path):
    """run should fail if neither --task nor --describe is provided."""
    csv_file = tmp_path / "input.csv"
    csv_file.write_text("url\nhttps://example.com\n")

    result = runner.invoke(app, ["run", "--input", str(csv_file)])
    assert result.exit_code != 0


def test_run_missing_input():
    """run should fail if input file does not exist."""
    result = runner.invoke(app, [
        "run", "--task", "fake.yaml", "--input", "/nonexistent/input.csv"
    ])
    assert result.exit_code != 0


def test_validate_valid(tmp_path):
    """validate should pass when all required columns exist."""
    csv_file = tmp_path / "input.csv"
    csv_file.write_text("url,summary\nhttps://example.com,test\n")

    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({
        "task_name": "test-task",
        "goal": "Test goal",
        "instructions": "Test instructions",
        "input_columns": ["url"],
        "output_schema": [{"name": "title", "description": "Page title"}],
    }))

    result = runner.invoke(app, [
        "validate", "--task", str(task_file), "--input", str(csv_file)
    ])
    assert result.exit_code == 0
    assert "Rows: 1" in result.output


def test_validate_missing_columns(tmp_path):
    """validate should fail when required columns are missing."""
    csv_file = tmp_path / "input.csv"
    csv_file.write_text("summary\ntest\n")

    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({
        "task_name": "test-task",
        "goal": "Test goal",
        "instructions": "Test instructions",
        "input_columns": ["url"],
        "output_schema": [{"name": "title", "description": "Page title"}],
    }))

    result = runner.invoke(app, [
        "validate", "--task", str(task_file), "--input", str(csv_file)
    ])
    assert result.exit_code == 1
    assert "url" in result.output


def test_resume_no_manifest(tmp_path):
    result = runner.invoke(app, ["resume", "--run-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "run_manifest.json" in result.output
