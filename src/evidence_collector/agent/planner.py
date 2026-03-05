"""Planning step: convert natural language descriptions into TaskDescription."""

from __future__ import annotations

import json
import os
from typing import Any

from evidence_collector.agent.task import TaskDescription


PLANNER_SYSTEM_PROMPT = """You are a task planning assistant for a browser-based evidence collection agent.

Given a natural language description of what evidence to collect, produce a structured TaskDescription.

You must call the create_task_description tool with the appropriate parameters. Think carefully about:
1. What input columns the user's CSV must have
2. What output fields need to be collected
3. Step-by-step instructions for the browser agent
4. Any constraints or rules

Be specific in the instructions — tell the agent exactly what pages to visit, what to look for, and what to screenshot."""


PLANNER_TOOL = {
    "name": "create_task_description",
    "description": "Create a structured task description for the evidence collection agent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task_name": {
                "type": "string",
                "description": "Short slug for directory names (e.g. 'github-checks', 'ticket-screenshots')",
            },
            "goal": {
                "type": "string",
                "description": "1-3 sentence description of the overall goal",
            },
            "instructions": {
                "type": "string",
                "description": "Detailed step-by-step instructions for the browser agent",
            },
            "input_columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Required column names in the input CSV",
            },
            "output_schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "required": {"type": "boolean", "default": True},
                    },
                    "required": ["name", "description"],
                },
                "description": "Output fields to collect",
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Hard rules the agent must follow",
            },
            "max_pages_per_sample": {
                "type": "integer",
                "default": 10,
                "description": "Maximum browser pages per sample",
            },
            "max_turns": {
                "type": "integer",
                "default": 30,
                "description": "Maximum LLM turns per sample",
            },
        },
        "required": ["task_name", "goal", "instructions", "input_columns", "output_schema"],
    },
}


async def plan_task(
    user_description: str,
    sample_row: dict | None = None,
    model: str = "claude-sonnet-4-20250514",
    api_key_env: str = "ANTHROPIC_API_KEY",
) -> TaskDescription:
    """Convert natural language into a structured TaskDescription via Claude.

    Args:
        user_description: Natural language description of what to collect.
        sample_row: Optional example row from the input CSV for context.
        model: Claude model to use for planning.
        api_key_env: Environment variable containing the API key.

    Returns:
        A validated TaskDescription.
    """
    import anthropic

    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"API key not found. Set {api_key_env}.")

    client = anthropic.AsyncAnthropic(api_key=api_key)

    user_msg = f"Create a task description for the following evidence collection task:\n\n{user_description}"
    if sample_row:
        user_msg += f"\n\nExample input row (column names and values):\n{json.dumps(sample_row, indent=2)}"

    response = await client.messages.create(
        model=model,
        system=PLANNER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=[PLANNER_TOOL],
        max_tokens=4096,
        temperature=0.0,
    )

    # Extract the tool call result
    for block in response.content:
        if block.type == "tool_use" and block.name == "create_task_description":
            return TaskDescription.model_validate(block.input)

    raise RuntimeError("Planner did not produce a task description")
