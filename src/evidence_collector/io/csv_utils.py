"""CSV output utilities for results files."""

from __future__ import annotations

from pathlib import Path


def init_results_csv(path: Path, columns: list[str]) -> None:
    """Create a results CSV with header row."""
    # TODO: write header row to new CSV file
    raise NotImplementedError


def append_result_row(path: Path, row: dict) -> None:
    """Append a single result row to an existing CSV."""
    # TODO: append row dict to CSV, matching column order from header
    raise NotImplementedError


def write_results_csv(path: Path, rows: list[dict]) -> None:
    """Write a complete results CSV from a list of row dicts."""
    # TODO: write all rows to CSV using pandas
    raise NotImplementedError
