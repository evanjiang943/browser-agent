"""Spreadsheet reading (CSV and XLSX)."""

from __future__ import annotations

from pathlib import Path


def read_input(path: Path) -> list[dict]:
    """Read a CSV or XLSX file and return a list of row dicts."""
    # TODO: detect file type, read with pandas, return list of dicts
    raise NotImplementedError


def validate_columns(rows: list[dict], required: list[str]) -> list[str]:
    """Validate that required columns exist. Return list of missing columns."""
    # TODO: check that all required columns are present in the data
    raise NotImplementedError
