"""Core agent loop: drives Claude API with tool calling."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from playwright.async_api import Page

from evidence_collector.adapters.browser import BrowserAdapter
from evidence_collector.agent.audit import ToolCallRecord, save_agent_trace
from evidence_collector.agent.prompts import (
    build_system_prompt,
    format_initial_prompt,
    resume_context_message,
)
from evidence_collector.agent.task import TaskDescription
from evidence_collector.agent.tools import build_tool_schemas, execute_tool
from evidence_collector.config import AgentConfig
from evidence_collector.evidence.logging import RunLogger
from evidence_collector.evidence.manifest import SampleNotes
from evidence_collector.io.paths import write_notes
from evidence_collector.utils.time import now_iso

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Mutable state for a single sample's agent run."""

    sample_id: str
    input: dict
    task: TaskDescription
    sample_dir: Path
    browser: BrowserAdapter
    run_logger: RunLogger
    config: AgentConfig
    screenshot_mode: str = "viewport"

    # Mutable state
    pages: dict[str, Page] = field(default_factory=dict)
    recorded_fields: dict[str, str] = field(default_factory=dict)
    field_provenance: dict[str, str | None] = field(default_factory=dict)
    notes: SampleNotes = field(default=None)  # type: ignore[assignment]
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    turn_count: int = 0
    last_screenshot_page_id: str | None = None
    on_progress: Callable[[dict], Awaitable[None]] | None = None

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = SampleNotes(sample_id=self.sample_id, status="pending")


async def run_agent_for_sample(
    ctx: AgentContext,
    client: Any,
) -> dict[str, str]:
    """Run the agent loop for a single sample.

    Args:
        ctx: Agent context with sample data, browser, and task description.
        client: Anthropic client instance (anthropic.AsyncAnthropic).

    Returns:
        Dict of recorded field values.
    """
    system = build_system_prompt(ctx.task)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": format_initial_prompt(ctx.task, ctx.input)}
    ]

    # Resumability: inject prior state
    if ctx.notes.result_data:
        ctx.recorded_fields.update(ctx.notes.result_data)
        messages.append(resume_context_message(ctx.notes))

    tools = build_tool_schemas()

    while ctx.turn_count < ctx.task.max_turns:
        ctx.turn_count += 1

        response = await client.messages.create(
            model=ctx.config.model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=4096,
            temperature=ctx.config.temperature,
        )

        ctx.run_logger.log(
            "llm_response",
            sample_id=ctx.sample_id,
            turn=ctx.turn_count,
            stop_reason=response.stop_reason,
        )

        # Check if the model wants to stop (no tool use)
        has_tool_use = any(
            block.type == "tool_use" for block in response.content
        )
        if not has_tool_use:
            break

        # Execute tool calls and collect results
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            result = await execute_tool(ctx, block.name, block.input)

            # Record the page URL for provenance
            page_url = None
            if ctx.pages:
                last_page_id = list(ctx.pages.keys())[-1]
                page_url = ctx.pages[last_page_id].url

            record = ToolCallRecord(
                turn=ctx.turn_count,
                tool_name=block.name,
                input=block.input,
                output=result,
                page_url=page_url,
            )
            ctx.tool_calls.append(record)

            ctx.run_logger.log(
                "tool_call",
                sample_id=ctx.sample_id,
                turn=ctx.turn_count,
                tool=block.name,
                success="error" not in result,
            )

            # Emit progress event if callback is set
            if ctx.on_progress:
                try:
                    await ctx.on_progress({
                        "event_type": "tool_call",
                        "sample_id": ctx.sample_id,
                        "tool_name": block.name,
                        "tool_params": block.input,
                        "tool_result": result,
                    })
                except Exception:
                    pass  # Never let a broken callback crash the agent

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        # Append assistant response and tool results to conversation
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        # Persist after each turn for crash-safe resumability
        ctx.notes.result_data = dict(ctx.recorded_fields)
        write_notes(ctx.sample_dir, ctx.notes.model_dump())

    # Post-loop: validate required fields
    missing = [
        f.name
        for f in ctx.task.output_schema
        if f.required and not ctx.recorded_fields.get(f.name)
    ]
    ctx.notes.status = "success" if not missing else "partial"
    ctx.notes.result_data = dict(ctx.recorded_fields)

    # Save agent trace
    trace_path = save_agent_trace(ctx.sample_dir, ctx.tool_calls)
    ctx.notes.agent_trace_file = str(trace_path.name)
    write_notes(ctx.sample_dir, ctx.notes.model_dump())

    # Close any remaining pages
    for page in ctx.pages.values():
        try:
            await page.close()
        except Exception:
            pass
    ctx.pages.clear()

    return dict(ctx.recorded_fields)
