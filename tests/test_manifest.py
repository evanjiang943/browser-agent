"""Tests for manifest creation and sample notes."""

import pytest
from pathlib import Path

from evidence_collector.evidence.manifest import (
    create_manifest,
    write_sample_notes,
    read_sample_notes,
)


def test_create_manifest_writes_json(tmp_path):
    """create_manifest should write a valid run_manifest.json."""
    # TODO: implement once create_manifest is implemented
    pass


def test_write_and_read_sample_notes(tmp_path):
    """write_sample_notes then read_sample_notes should round-trip."""
    # TODO: implement
    pass


def test_read_sample_notes_missing_returns_none(tmp_path):
    """read_sample_notes on a non-existent path should return None."""
    # TODO: implement
    pass
