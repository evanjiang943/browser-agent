"""Spreadsheet reading (CSV and XLSX)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from evidence_collector.evidence.naming import generate_sample_id


def read_input(path: Path) -> list[dict]:
    """Read a CSV or XLSX file and return a list of row dicts."""
    path = Path(path)
    if path.suffix == ".csv":
        df = pd.read_csv(path)
    elif path.suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    return df.to_dict(orient="records")


def validate_columns(rows: list[dict], required: list[str]) -> list[str]:
    """Validate that required columns exist. Return list of missing columns."""
    if not rows:
        return list(required)
    present = set(rows[0].keys())
    return [c for c in required if c not in present]


_REQUIRED_COLUMN_SETS = [{"pr_url"}, {"commit_url"}, {"repo", "sha"}]


def load_github_samples(input_path: Path) -> list[dict]:
    """Load and normalize GitHub PR/commit rows from CSV/XLSX.

    Requires at least one of: ``pr_url``, ``commit_url``, or both ``repo`` + ``sha``.
    Returns dicts with ``sample_id``, ``github_url``, ``pr_or_commit`` plus original row data.
    """
    rows = read_input(input_path)
    if not rows:
        return []

    columns = set(rows[0].keys())
    if not any(req <= columns for req in _REQUIRED_COLUMN_SETS):
        raise ValueError(
            f"Missing required columns. Found: {sorted(columns)}. "
            f"Need one of: pr_url, commit_url, or repo+sha"
        )

    results: list[dict] = []
    for i, row in enumerate(rows):
        pr_url = _nonempty(row.get("pr_url"))
        commit_url = _nonempty(row.get("commit_url"))
        repo = _nonempty(row.get("repo"))
        sha = _nonempty(row.get("sha"))

        if pr_url:
            github_url = pr_url
            pr_or_commit = "pr"
        elif commit_url:
            github_url = commit_url
            pr_or_commit = "commit"
        elif repo and sha:
            github_url = f"https://github.com/{repo}/commit/{sha}"
            pr_or_commit = "commit"
        else:
            raise ValueError(f"Row {i}: no usable GitHub URL (need pr_url, commit_url, or repo+sha)")

        sample_id = _extract_sample_id(github_url, pr_or_commit)
        results.append({**row, "sample_id": sample_id, "github_url": github_url, "pr_or_commit": pr_or_commit})

    return results


def _nonempty(value: object) -> str | None:
    """Return stripped string if non-empty, else None."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s.lower() != "nan" else None


def _extract_sample_id(url: str, pr_or_commit: str) -> str:
    """Extract a sample ID from a GitHub URL."""
    if pr_or_commit == "pr":
        m = re.search(r"/pull/(\d+)", url)
        if m:
            return f"pr-{m.group(1)}"
    else:
        # Last path segment is the sha
        sha = url.rstrip("/").rsplit("/", 1)[-1]
        if re.fullmatch(r"[0-9a-fA-F]{7,40}", sha):
            return sha[:12]
    return generate_sample_id(url=url)
