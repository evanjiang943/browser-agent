"""CSV output utilities for results files."""

from __future__ import annotations

import csv
from pathlib import Path


def init_results_csv(path: Path, columns: list[str]) -> None:
    """Create a results CSV with header row."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)


def append_result_row(path: Path, row: dict) -> None:
    """Append a single result row to an existing CSV.

    Reads the header from the file, then appends a row matching column
    order.  Missing keys produce empty strings.
    """
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        columns = next(reader)

    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row.get(col, "") for col in columns)


def write_results_csv(path: Path, rows: list[dict]) -> None:
    """Write a complete results CSV from a list of row dicts.

    Columns are derived from the union of all row keys, ordered by first
    appearance.
    """
    if not rows:
        path.write_text("")
        return

    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                columns.append(key)
                seen.add(key)

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
