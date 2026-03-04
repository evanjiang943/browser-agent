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


_DEFAULT_WINDOW_DAYS = 365


def load_code_recency_samples(input_path: Path) -> list[dict]:
    """Load code recency samples from CSV/XLSX.

    Requires columns: ``repo_url``, ``code_string``.
    Optional: ``time_window_days`` (int, default 365), ``since_date`` (str).
    Returns dicts with ``sample_id``, ``repo_url``, ``code_string``,
    ``time_window_days`` plus original row data.
    """
    rows = read_input(input_path)
    if not rows:
        return []

    missing = validate_columns(rows, ["repo_url", "code_string"])
    if missing:
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}. "
            f"Need: repo_url, code_string"
        )

    results: list[dict] = []
    for row in rows:
        repo_url = _nonempty(row.get("repo_url"))
        code_string = _nonempty(row.get("code_string"))
        if not repo_url or not code_string:
            continue

        sample_id = generate_sample_id(url=f"{repo_url}|{code_string}")

        # Parse time window: prefer time_window_days, fall back to since_date
        raw_window = _nonempty(row.get("time_window_days"))
        raw_since = _nonempty(row.get("since_date"))

        if raw_window is not None:
            try:
                time_window_days = int(float(raw_window))
            except (ValueError, TypeError):
                time_window_days = _DEFAULT_WINDOW_DAYS
        elif raw_since is not None:
            # Convert since_date to days from now
            from datetime import datetime, timezone
            try:
                since = datetime.fromisoformat(raw_since)
                if since.tzinfo is None:
                    since = since.replace(tzinfo=timezone.utc)
                delta = datetime.now(timezone.utc) - since
                time_window_days = max(1, delta.days)
            except (ValueError, TypeError):
                time_window_days = _DEFAULT_WINDOW_DAYS
        else:
            time_window_days = _DEFAULT_WINDOW_DAYS

        results.append({
            **row,
            "sample_id": sample_id,
            "repo_url": repo_url,
            "code_string": code_string,
            "time_window_days": time_window_days,
        })

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
