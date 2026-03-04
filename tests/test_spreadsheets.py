"""Tests for spreadsheet reading and validation."""

import pytest
from pathlib import Path

from evidence_collector.io.spreadsheets import read_input, validate_columns, load_github_samples


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


def test_load_github_samples_missing_columns(tmp_path):
    """load_github_samples should raise ValueError when no required columns exist."""
    csv = tmp_path / "bad.csv"
    csv.write_text("name,age\nAlice,30\n")
    with pytest.raises(ValueError, match="Missing required columns"):
        load_github_samples(csv)


def test_load_github_samples_prefers_pr_url(tmp_path):
    """load_github_samples should prefer pr_url over commit_url."""
    csv = tmp_path / "both.csv"
    csv.write_text(
        "pr_url,commit_url\n"
        "https://github.com/org/repo/pull/42,https://github.com/org/repo/commit/abc123def456\n"
    )
    rows = load_github_samples(csv)
    assert len(rows) == 1
    assert rows[0]["github_url"] == "https://github.com/org/repo/pull/42"
    assert rows[0]["pr_or_commit"] == "pr"
    assert rows[0]["sample_id"] == "pr-42"


def test_load_github_samples_stable_ids(tmp_path):
    """load_github_samples should produce identical sample_ids across calls."""
    csv = tmp_path / "stable.csv"
    csv.write_text("pr_url\nhttps://github.com/org/repo/pull/99\n")
    first = load_github_samples(csv)
    second = load_github_samples(csv)
    assert first[0]["sample_id"] == second[0]["sample_id"]


def test_load_github_samples_repo_sha(tmp_path):
    """load_github_samples should construct commit URL from repo + sha."""
    csv = tmp_path / "repo_sha.csv"
    sha = "abcdef1234567890abcdef1234567890abcdef12"
    csv.write_text(f"repo,sha\norg/myrepo,{sha}\n")
    rows = load_github_samples(csv)
    assert len(rows) == 1
    assert rows[0]["github_url"] == f"https://github.com/org/myrepo/commit/{sha}"
    assert rows[0]["pr_or_commit"] == "commit"
    assert rows[0]["sample_id"] == sha[:12]
