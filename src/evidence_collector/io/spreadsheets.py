"""Spreadsheet reading (CSV and XLSX)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


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
