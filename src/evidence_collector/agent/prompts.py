"""Prompt construction for the LLM agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evidence_collector.agent.task import TaskDescription
    from evidence_collector.evidence.manifest import SampleNotes


def build_system_prompt(task: TaskDescription) -> str:
    """Construct the system prompt for the agent."""
    schema_lines = []
    for f in task.output_schema:
        req = "REQUIRED" if f.required else "optional"
        schema_lines.append(f"  - {f.name} ({req}): {f.description}")
    schema_block = "\n".join(schema_lines)

    constraints_block = ""
    if task.constraints:
        constraints_block = "\n\nHard constraints:\n" + "\n".join(
            f"  - {c}" for c in task.constraints
        )

    return f"""You are a browser-based evidence collection agent. Your job is to navigate web pages, collect evidence (screenshots, downloads), and extract structured data.

## Task
{task.goal}

## Output Schema
You must record values for each of these fields using the record_field tool:
{schema_block}

## Instructions
{task.instructions}{constraints_block}

## Rules
- Use take_screenshot to capture visual evidence BEFORE extracting data from a page.
- Use record_field to save each extracted value. Only field names from the output schema are accepted.
- Use get_required_fields to check progress.
- When all required fields are filled (or cannot be found), stop by responding without tool calls.
- Do NOT fabricate values. If you cannot find a value on the page, record an empty string.
- You have a maximum of {task.max_turns} turns and can open up to {task.max_pages_per_sample} pages.
- Close pages you no longer need to free resources."""


def format_initial_prompt(task: TaskDescription, sample_input: dict) -> str:
    """Construct the initial user message for a sample."""
    input_lines = []
    for key, value in sample_input.items():
        input_lines.append(f"  {key}: {value}")
    input_block = "\n".join(input_lines)

    return f"""Collect evidence for this sample:

{input_block}

Begin by navigating to the relevant URL(s) and collecting the required data."""


def resume_context_message(notes: SampleNotes) -> dict:
    """Construct a message injecting prior state for resumed samples."""
    lines = ["This sample was partially processed in a previous run."]

    if notes.result_data:
        lines.append("\nPreviously recorded fields:")
        for key, value in notes.result_data.items():
            lines.append(f"  {key}: {value}")

    if notes.screenshots:
        lines.append(f"\nScreenshots already taken: {len(notes.screenshots)}")

    if notes.errors:
        lines.append("\nPrevious errors:")
        for err in notes.errors:
            lines.append(f"  - {err}")

    lines.append("\nContinue collecting any missing fields.")

    return {"role": "user", "content": "\n".join(lines)}
