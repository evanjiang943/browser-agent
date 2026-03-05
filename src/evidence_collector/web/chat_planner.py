"""Multi-turn conversational planner for the web UI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from evidence_collector.agent.planner import PLANNER_SYSTEM_PROMPT, PLANNER_TOOL
from evidence_collector.agent.task import TaskDescription


CHAT_PLANNER_SYSTEM_PROMPT = PLANNER_SYSTEM_PROMPT + """

IMPORTANT ADDITIONS FOR CONVERSATIONAL MODE:
- You are chatting with an auditor who may not know the exact technical details.
- Ask clarifying questions before calling the tool if the description is ambiguous.
- For example, ask about: what specific data to extract, which columns exist in their CSV,
  what URLs to visit, what screenshots to take, any login requirements, etc.
- Only call the create_task_description tool when you have enough information to build a complete task.
- Keep your responses concise and friendly.
- If the user provides a CSV with column names, use those to inform input_columns."""


@dataclass
class ChatPlannerResult:
    """Result of a single planner turn."""

    text: str | None  # Chat response text (if any)
    task: TaskDescription | None  # Produced task (if tool was called)


async def chat_planner_turn(
    messages: list[dict[str, Any]],
    user_text: str,
    sample_row: dict | None = None,
    model: str = "claude-sonnet-4-20250514",
    api_key_env: str = "ANTHROPIC_API_KEY",
) -> ChatPlannerResult:
    """Run one turn of the conversational planner.

    Appends user message to `messages` (mutated in place), calls Claude,
    appends assistant response, and returns any text + optional TaskDescription.
    """
    import anthropic

    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"API key not found. Set {api_key_env}.")

    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Build user message with optional CSV context
    content = user_text
    if sample_row and not messages:
        content += f"\n\nThe uploaded CSV has these columns and sample values:\n{json.dumps(sample_row, indent=2)}"

    messages.append({"role": "user", "content": content})

    response = await client.messages.create(
        model=model,
        system=CHAT_PLANNER_SYSTEM_PROMPT,
        messages=messages,
        tools=[PLANNER_TOOL],
        max_tokens=4096,
        temperature=0.0,
    )

    # Extract text and tool_use blocks
    text_parts = []
    task = None

    assistant_content = response.content
    messages.append({"role": "assistant", "content": assistant_content})

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use" and block.name == "create_task_description":
            task = TaskDescription.model_validate(block.input)
            # Append tool_result so conversation stays valid
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps({"status": "preview_shown_to_user"}),
                }],
            })

    return ChatPlannerResult(
        text="\n".join(text_parts) if text_parts else None,
        task=task,
    )
