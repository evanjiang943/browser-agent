"""Tests for evidence naming utilities."""

import re
from unittest.mock import patch

import pytest

from evidence_collector.evidence.naming import (
    generate_sample_id,
    safe_folder_name,
    screenshot_filename,
)


# --- generate_sample_id ---

def test_sample_id_from_primary_key():
    """Sample ID from a primary key should be deterministic, lowercase, and filesystem-safe."""
    sid = generate_sample_id(primary_key="MyTicket123")
    assert sid == "myticket123"
    assert sid == generate_sample_id(primary_key="MyTicket123")


def test_sample_id_from_primary_key_special_chars():
    """Special characters are replaced with dashes and collapsed."""
    assert generate_sample_id(primary_key="ENG-101") == "eng-101"
    assert generate_sample_id(primary_key="My Ticket / 2") == "my-ticket-2"


def test_sample_id_from_url():
    """Sample ID from a URL should be a 12-char hex string, stable across calls."""
    sid = generate_sample_id(url="https://example.com/page")
    assert len(sid) == 12
    assert re.fullmatch(r"[0-9a-f]{12}", sid)
    assert sid == generate_sample_id(url="https://example.com/page")


def test_sample_id_url_uniqueness():
    """Different URLs should produce different IDs."""
    id1 = generate_sample_id(url="https://example.com/a")
    id2 = generate_sample_id(url="https://example.com/b")
    assert id1 != id2


def test_sample_id_no_input_raises():
    """ValueError when no arguments are provided."""
    with pytest.raises(ValueError):
        generate_sample_id()


def test_sample_id_primary_key_priority():
    """primary_key takes priority over url."""
    sid = generate_sample_id(primary_key="ticket-1", url="https://example.com")
    assert sid == "ticket-1"


# --- screenshot_filename ---

@patch("evidence_collector.evidence.naming.now_filename_stamp", return_value="20260304-120000")
def test_screenshot_filename_format(mock_ts):
    """Filename should have __ delimiters, end with .png, and contain all parts."""
    fname = screenshot_filename("sample1", "systemA", "login")
    assert fname == "sample1__systemA__login__20260304-120000__0.png"
    parts = fname.rsplit(".png", 1)[0].split("__")
    assert len(parts) == 5


@patch("evidence_collector.evidence.naming.now_filename_stamp", return_value="20260304-120000")
def test_screenshot_filename_index(mock_ts):
    """Different index values should appear in the filename."""
    f0 = screenshot_filename("s", "sys", "step", index=0)
    f3 = screenshot_filename("s", "sys", "step", index=3)
    assert "__0.png" in f0
    assert "__3.png" in f3


# --- safe_folder_name ---

def test_safe_folder_name_slashes():
    """Forward and backslashes are replaced."""
    assert safe_folder_name("a/b\\c") == "a-b-c"


def test_safe_folder_name_spaces():
    """Spaces become dashes."""
    assert safe_folder_name("hello world") == "hello-world"


def test_safe_folder_name_unicode():
    """Non-ASCII characters are kept (only unsafe FS chars are replaced)."""
    result = safe_folder_name("café résumé")
    assert "café" in result
    assert " " not in result


def test_safe_folder_name_empty():
    """Empty or all-unsafe input returns '_unnamed'."""
    assert safe_folder_name("") == "_unnamed"
    assert safe_folder_name("///") == "_unnamed"
