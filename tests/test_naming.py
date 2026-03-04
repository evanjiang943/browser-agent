"""Tests for evidence naming utilities."""

import pytest

from evidence_collector.evidence.naming import (
    generate_sample_id,
    safe_folder_name,
    screenshot_filename,
)


def test_generate_sample_id_from_primary_key():
    """Sample ID from a primary key should be deterministic and filesystem-safe."""
    # TODO: implement once generate_sample_id is implemented
    pass


def test_generate_sample_id_from_url():
    """Sample ID from a URL should be a stable hash."""
    # TODO: implement
    pass


def test_screenshot_filename_format():
    """Screenshot filename should follow naming convention."""
    # TODO: implement once screenshot_filename is implemented
    pass


def test_safe_folder_name_removes_unsafe_chars():
    """Unsafe characters should be stripped or replaced."""
    # TODO: implement
    pass
