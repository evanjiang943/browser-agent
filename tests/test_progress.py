"""Tests for web progress events and message templates."""

from evidence_collector.web.progress import ProgressEvent, tool_progress_message


def test_progress_event_defaults():
    e = ProgressEvent(event_type="tool_call")
    assert e.event_type == "tool_call"
    assert e.sample_id == ""
    assert e.tool_name == ""
    assert e.message == ""


def test_progress_event_full():
    e = ProgressEvent(
        event_type="sample_start",
        sample_id="abc",
        sample_index=2,
        total_samples=10,
        message="Starting sample 3/10",
    )
    assert e.sample_index == 2
    assert e.total_samples == 10


def test_tool_progress_open_url():
    msg = tool_progress_message("open_url", {"url": "https://example.com"})
    assert "https://example.com" in msg


def test_tool_progress_take_screenshot():
    msg = tool_progress_message("take_screenshot", {"label": "overview", "page_id": "page_0"})
    assert "overview" in msg


def test_tool_progress_record_field():
    msg = tool_progress_message("record_field", {"field_name": "status", "value": "active"})
    assert "status" in msg
    assert "active" in msg


def test_tool_progress_read_page():
    msg = tool_progress_message("read_page_text", {"page_id": "page_0"})
    assert "Reading" in msg


def test_tool_progress_scroll():
    msg = tool_progress_message("scroll_page", {"page_id": "page_0", "direction": "down"})
    assert "down" in msg


def test_tool_progress_unknown():
    msg = tool_progress_message("unknown_tool", {})
    assert "unknown_tool" in msg


def test_tool_progress_missing_param():
    """Template with missing key falls back gracefully."""
    msg = tool_progress_message("open_url", {})
    assert "open_url" in msg


def test_tool_progress_click():
    msg = tool_progress_message("click_element", {"page_id": "page_0", "selector": "#btn"})
    assert "page_0" in msg


def test_tool_progress_find_links():
    msg = tool_progress_message("find_links", {"page_id": "p0", "url_pattern": ".*"})
    assert "links" in msg.lower() or "Searching" in msg


def test_tool_progress_evaluate_js():
    msg = tool_progress_message("evaluate_js", {"page_id": "p0", "expression": "1+1"})
    assert "JavaScript" in msg


def test_tool_progress_save_download():
    msg = tool_progress_message("save_download", {"filename": "report.pdf", "page_id": "p0", "click_selector": "a"})
    assert "report.pdf" in msg


def test_tool_progress_get_fields():
    msg = tool_progress_message("get_required_fields", {})
    assert "required" in msg.lower() or "fields" in msg.lower()
