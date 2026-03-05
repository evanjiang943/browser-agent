"""Tests for spreadsheet reading and validation."""

import pytest
from pathlib import Path

from evidence_collector.io.spreadsheets import read_input, validate_columns


def test_read_csv(tmp_path):
    """read_input should parse a CSV file into row dicts."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("name,age\nAlice,30\nBob,25\n")
    rows = read_input(csv_file)
    assert len(rows) == 2
    assert rows[0]["name"] == "Alice"
    assert rows[1]["age"] == 25


def test_read_unsupported(tmp_path):
    """read_input should raise ValueError for unsupported file types."""
    txt_file = tmp_path / "data.txt"
    txt_file.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported file type"):
        read_input(txt_file)


def test_validate_columns_all_present():
    """validate_columns should return empty list when all required columns exist."""
    rows = [{"url": "https://example.com", "name": "test"}]
    missing = validate_columns(rows, ["url", "name"])
    assert missing == []


def test_validate_columns_missing():
    """validate_columns should return list of missing column names."""
    rows = [{"name": "test"}]
    missing = validate_columns(rows, ["url", "name"])
    assert missing == ["url"]


def test_validate_columns_empty_rows():
    """validate_columns should return all required columns when rows are empty."""
    missing = validate_columns([], ["url", "name"])
    assert missing == ["url", "name"]
