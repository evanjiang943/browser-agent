"""Tests for agent audit trail."""

import json

from evidence_collector.agent.audit import (
    ToolCallRecord,
    load_agent_trace,
    save_agent_trace,
    verify_trace,
)


def test_tool_call_record_defaults():
    r = ToolCallRecord(
        turn=1,
        tool_name="open_url",
        input={"url": "https://example.com"},
        output={"page_id": "page_0"},
    )
    assert r.turn == 1
    assert r.timestamp  # auto-populated


def test_save_and_load_trace(tmp_path):
    records = [
        ToolCallRecord(
            turn=1,
            tool_name="open_url",
            input={"url": "https://example.com"},
            output={"page_id": "page_0"},
        ),
        ToolCallRecord(
            turn=2,
            tool_name="read_page_text",
            input={"page_id": "page_0"},
            output={"text": "Hello world", "truncated": False},
        ),
    ]
    path = save_agent_trace(tmp_path, records)
    assert path.exists()

    loaded = load_agent_trace(tmp_path)
    assert len(loaded) == 2
    assert loaded[0].tool_name == "open_url"
    assert loaded[1].tool_name == "read_page_text"


def test_load_trace_missing(tmp_path):
    loaded = load_agent_trace(tmp_path)
    assert loaded == []


def test_verify_trace_clean(tmp_path):
    """Verify returns no warnings when recorded values are in page text."""
    records = [
        ToolCallRecord(
            turn=1,
            tool_name="read_page_text",
            input={"page_id": "page_0"},
            output={"text": "Title: My Page\nStatus: Open"},
        ),
        ToolCallRecord(
            turn=2,
            tool_name="record_field",
            input={"field_name": "title", "value": "My Page"},
            output={"success": True},
        ),
    ]
    save_agent_trace(tmp_path, records)
    warnings = verify_trace(tmp_path)
    assert warnings == []


def test_verify_trace_hallucination(tmp_path):
    """Verify flags values not found in observed text."""
    records = [
        ToolCallRecord(
            turn=1,
            tool_name="read_page_text",
            input={"page_id": "page_0"},
            output={"text": "Some page content"},
        ),
        ToolCallRecord(
            turn=2,
            tool_name="record_field",
            input={"field_name": "title", "value": "Fabricated Value"},
            output={"success": True},
        ),
    ]
    save_agent_trace(tmp_path, records)
    warnings = verify_trace(tmp_path)
    assert len(warnings) == 1
    assert "Fabricated Value" in warnings[0]


def test_verify_trace_query_selector_text(tmp_path):
    """Verify also checks query_selector_text outputs."""
    records = [
        ToolCallRecord(
            turn=1,
            tool_name="query_selector_text",
            input={"page_id": "page_0", "selector": "h1"},
            output={"found": True, "text": "Real Title"},
        ),
        ToolCallRecord(
            turn=2,
            tool_name="record_field",
            input={"field_name": "title", "value": "Real Title"},
            output={"success": True},
        ),
    ]
    save_agent_trace(tmp_path, records)
    warnings = verify_trace(tmp_path)
    assert warnings == []
