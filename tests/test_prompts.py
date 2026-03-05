"""Tests for agent prompt construction."""

from evidence_collector.agent.prompts import (
    build_system_prompt,
    format_initial_prompt,
    resume_context_message,
)
from evidence_collector.agent.task import OutputField, TaskDescription
from evidence_collector.evidence.manifest import SampleNotes


def _make_task():
    return TaskDescription(
        task_name="test",
        goal="Collect page data",
        instructions="Open URL and extract info",
        input_columns=["url"],
        output_schema=[
            OutputField(name="title", description="Page title"),
            OutputField(name="notes", description="Extra notes", required=False),
        ],
        constraints=["Screenshot before extracting"],
        max_turns=20,
    )


def test_build_system_prompt():
    task = _make_task()
    prompt = build_system_prompt(task)
    assert "Collect page data" in prompt
    assert "title (REQUIRED)" in prompt
    assert "notes (optional)" in prompt
    assert "Screenshot before extracting" in prompt
    assert "record_field" in prompt
    assert "20" in prompt  # max_turns


def test_format_initial_prompt():
    task = _make_task()
    prompt = format_initial_prompt(task, {"url": "https://example.com", "name": "test"})
    assert "https://example.com" in prompt
    assert "test" in prompt
    assert "Collect evidence" in prompt


def test_resume_context_message():
    notes = SampleNotes(
        sample_id="sample-1",
        status="partial",
        result_data={"title": "Existing"},
        screenshots=["shot1.png"],
        errors=["timeout"],
    )
    msg = resume_context_message(notes)
    assert msg["role"] == "user"
    assert "Existing" in msg["content"]
    assert "1" in msg["content"]  # screenshot count
    assert "timeout" in msg["content"]
