"""Tests for the agent loop with mock Claude responses."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from evidence_collector.agent.loop import AgentContext, run_agent_for_sample
from evidence_collector.agent.task import OutputField, TaskDescription
from evidence_collector.config import AgentConfig
from evidence_collector.evidence.manifest import SampleNotes


@pytest.fixture
def task():
    return TaskDescription(
        task_name="test",
        goal="Collect page title",
        instructions="Open the URL and extract the title",
        input_columns=["url"],
        output_schema=[
            OutputField(name="title", description="Page title"),
            OutputField(name="extra", description="Extra info", required=False),
        ],
        max_turns=5,
    )


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example")
    page.inner_text = AsyncMock(return_value="Page text with Title Here")
    page.query_selector.return_value = None
    page.close = AsyncMock()
    page.viewport_size = {"width": 1280, "height": 720}
    return page


@pytest.fixture
def mock_browser(mock_page):
    browser = AsyncMock()
    browser.open = AsyncMock(return_value=mock_page)
    browser.screenshot = AsyncMock()
    browser.close = AsyncMock()
    browser.timeout = 30000
    return browser


@pytest.fixture
def ctx(task, mock_browser, tmp_path):
    sample_dir = tmp_path / "sample-1"
    sample_dir.mkdir()
    (sample_dir / "screenshots").mkdir()
    (sample_dir / "downloads").mkdir()

    return AgentContext(
        sample_id="sample-1",
        input={"url": "https://example.com"},
        task=task,
        sample_dir=sample_dir,
        browser=mock_browser,
        run_logger=MagicMock(),
        config=AgentConfig(),
    )


def _make_response(content_blocks, stop_reason="end_turn"):
    """Build a mock Claude API response."""
    response = MagicMock()
    response.content = content_blocks
    response.stop_reason = stop_reason
    return response


def _text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _tool_use_block(tool_id, name, input_data):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_data
    return block


class TestRunAgentForSample:
    def test_immediate_stop(self, ctx):
        """Agent stops immediately when model returns end_turn."""
        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=_make_response(
            [_text_block("No tools needed")],
            stop_reason="end_turn",
        ))
        result = asyncio.run(run_agent_for_sample(ctx, client))
        assert ctx.notes.status == "partial"  # required fields missing

    def test_tool_use_then_stop(self, ctx, mock_page):
        """Agent calls record_field then stops."""
        mock_page.title = AsyncMock(return_value="Example")

        # Turn 1: open_url + record_field
        turn1 = _make_response([
            _tool_use_block("t1", "open_url", {"url": "https://example.com"}),
            _tool_use_block("t2", "record_field", {"field_name": "title", "value": "Example"}),
        ], stop_reason="tool_use")

        # Turn 2: done
        turn2 = _make_response(
            [_text_block("Done collecting")],
            stop_reason="end_turn",
        )

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=[turn1, turn2])

        result = asyncio.run(run_agent_for_sample(ctx, client))
        assert result["title"] == "Example"
        assert ctx.notes.status == "success"

    def test_max_turns_enforced(self, ctx, mock_page):
        """Agent should stop after max_turns even if it keeps calling tools."""
        mock_page.title = AsyncMock(return_value="Example")
        ctx.task.max_turns = 2

        # Both turns return tool calls
        tool_response = _make_response([
            _tool_use_block("t1", "get_required_fields", {}),
        ], stop_reason="tool_use")

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=tool_response)

        result = asyncio.run(run_agent_for_sample(ctx, client))
        assert ctx.turn_count == 2
        assert ctx.notes.status == "partial"

    def test_notes_persisted_each_turn(self, ctx, mock_page):
        """notes.json should be written after each tool-use turn."""
        mock_page.title = AsyncMock(return_value="Example")

        turn1 = _make_response([
            _tool_use_block("t1", "record_field", {"field_name": "title", "value": "T"}),
        ], stop_reason="tool_use")
        turn2 = _make_response([_text_block("Done")], stop_reason="end_turn")

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=[turn1, turn2])

        asyncio.run(run_agent_for_sample(ctx, client))

        notes_path = ctx.sample_dir / "notes.json"
        assert notes_path.exists()
        notes = json.loads(notes_path.read_text())
        assert notes["result_data"]["title"] == "T"

    def test_trace_saved(self, ctx, mock_page):
        """agent_trace.jsonl should be saved after the loop."""
        mock_page.title = AsyncMock(return_value="Example")

        turn1 = _make_response([
            _tool_use_block("t1", "open_url", {"url": "https://example.com"}),
        ], stop_reason="tool_use")
        turn2 = _make_response([_text_block("Done")], stop_reason="end_turn")

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=[turn1, turn2])

        asyncio.run(run_agent_for_sample(ctx, client))

        trace_path = ctx.sample_dir / "agent_trace.jsonl"
        assert trace_path.exists()
        lines = trace_path.read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["tool_name"] == "open_url"

    def test_resumability_with_prior_data(self, ctx):
        """Agent should include prior data when resuming."""
        ctx.notes.result_data = {"title": "Already collected"}

        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=_make_response(
            [_text_block("Nothing more to do")],
            stop_reason="end_turn",
        ))

        result = asyncio.run(run_agent_for_sample(ctx, client))
        assert result["title"] == "Already collected"
        # Check that 3 messages were sent (initial + resume context)
        call_kwargs = client.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        assert len(messages) == 2  # initial prompt + resume context

    def test_pages_closed_on_completion(self, ctx, mock_page):
        """All pages should be closed after the loop finishes."""
        mock_page.title = AsyncMock(return_value="Example")

        turn1 = _make_response([
            _tool_use_block("t1", "open_url", {"url": "https://example.com"}),
        ], stop_reason="tool_use")
        turn2 = _make_response([_text_block("Done")], stop_reason="end_turn")

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=[turn1, turn2])

        asyncio.run(run_agent_for_sample(ctx, client))
        assert len(ctx.pages) == 0
        mock_page.close.assert_called()
