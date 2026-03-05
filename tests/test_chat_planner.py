"""Tests for multi-turn conversational planner."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evidence_collector.web.chat_planner import (
    CHAT_PLANNER_SYSTEM_PROMPT,
    ChatPlannerResult,
    chat_planner_turn,
)


def _make_text_block(text):
    return SimpleNamespace(type="text", text=text)


def _make_tool_use_block(tool_input):
    return SimpleNamespace(
        type="tool_use",
        name="create_task_description",
        id="call_123",
        input=tool_input,
    )


def _mock_anthropic(mock_client):
    """Create a mock anthropic module and inject it into sys.modules."""
    mock_module = MagicMock()
    mock_module.AsyncAnthropic.return_value = mock_client
    return mock_module


@pytest.mark.asyncio
async def test_chat_turn_text_only():
    """Planner responds with text only (asking clarifying question)."""
    mock_response = SimpleNamespace(
        content=[_make_text_block("What columns does your CSV have?")],
        stop_reason="end_turn",
    )
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_mod = _mock_anthropic(mock_client)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), \
         patch.dict(sys.modules, {"anthropic": mock_mod}):
        messages = []
        result = await chat_planner_turn(messages, "I need screenshots of GitHub repos")

    assert result.text == "What columns does your CSV have?"
    assert result.task is None
    assert len(messages) == 2  # user + assistant


@pytest.mark.asyncio
async def test_chat_turn_with_tool_call():
    """Planner calls the tool to produce a TaskDescription."""
    task_input = {
        "task_name": "github-screenshots",
        "goal": "Take screenshots of GitHub repos",
        "instructions": "Open each repo URL and screenshot the main page",
        "input_columns": ["url"],
        "output_schema": [
            {"name": "screenshot_taken", "description": "Whether screenshot was taken"}
        ],
    }

    mock_response = SimpleNamespace(
        content=[
            _make_text_block("Here's the task I've created:"),
            _make_tool_use_block(task_input),
        ],
        stop_reason="tool_use",
    )
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_mod = _mock_anthropic(mock_client)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), \
         patch.dict(sys.modules, {"anthropic": mock_mod}):
        messages = []
        result = await chat_planner_turn(messages, "Screenshot GitHub repos listed in my CSV")

    assert result.text == "Here's the task I've created:"
    assert result.task is not None
    assert result.task.task_name == "github-screenshots"
    assert len(result.task.output_schema) == 1
    # Messages should include user, assistant, and tool_result
    assert len(messages) == 3


@pytest.mark.asyncio
async def test_chat_turn_no_api_key():
    """Raises RuntimeError when API key is missing."""
    mock_mod = MagicMock()
    with patch.dict("os.environ", {}, clear=True), \
         patch.dict(sys.modules, {"anthropic": mock_mod}):
        with pytest.raises(RuntimeError, match="API key"):
            await chat_planner_turn([], "hello")


def test_system_prompt_includes_conversational_instructions():
    """The chat planner prompt extends the base planner prompt."""
    assert "clarifying questions" in CHAT_PLANNER_SYSTEM_PROMPT
    assert "create_task_description" in CHAT_PLANNER_SYSTEM_PROMPT or "task" in CHAT_PLANNER_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_chat_turn_with_sample_row_first_turn():
    """First turn includes sample row context."""
    mock_response = SimpleNamespace(
        content=[_make_text_block("I see your CSV has a 'url' column.")],
        stop_reason="end_turn",
    )
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_mod = _mock_anthropic(mock_client)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), \
         patch.dict(sys.modules, {"anthropic": mock_mod}):
        messages = []
        result = await chat_planner_turn(
            messages, "Check repos",
            sample_row={"url": "https://github.com/example/repo"},
        )

    # The first message should contain the sample row
    call_args = mock_client.messages.create.call_args
    user_content = call_args.kwargs["messages"][0]["content"]
    assert "url" in user_content
    assert "github.com" in user_content
