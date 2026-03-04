"""Tests for spreadsheet reading and validation."""

import pytest
from pathlib import Path

from evidence_collector.io.spreadsheets import read_input, validate_columns


def test_read_csv(tmp_path):
    """read_input should parse a CSV file into row dicts."""
    # TODO: create a temp CSV, read it, verify contents
    pass


def test_read_xlsx(tmp_path):
    """read_input should parse an XLSX file into row dicts."""
    # TODO: create a temp XLSX, read it, verify contents
    pass


def test_validate_columns_all_present():
    """validate_columns should return empty list when all required columns exist."""
    # TODO: implement
    pass


def test_validate_columns_missing():
    """validate_columns should return list of missing column names."""
    # TODO: implement
    pass
