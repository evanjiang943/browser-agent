"""Audit trail: tool call recording, trace persistence, post-hoc verification."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from evidence_collector.utils.time import now_iso


class ToolCallRecord(BaseModel):
    """A single tool invocation in the agent trace."""

    turn: int
    tool_name: str
    input: dict
    output: dict
    page_url: str | None = None
    timestamp: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.timestamp:
            self.timestamp = now_iso()


def save_agent_trace(sample_dir: Path, tool_calls: list[ToolCallRecord]) -> Path:
    """Write tool call records to agent_trace.jsonl in the sample directory.

    Uses atomic write for crash safety. Returns the trace file path.
    """
    dest = sample_dir / "agent_trace.jsonl"
    fd, tmp_path = tempfile.mkstemp(dir=sample_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            for record in tool_calls:
                f.write(record.model_dump_json() + "\n")
        os.replace(tmp_path, dest)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return dest


def load_agent_trace(sample_dir: Path) -> list[ToolCallRecord]:
    """Load tool call records from agent_trace.jsonl."""
    trace_path = sample_dir / "agent_trace.jsonl"
    if not trace_path.exists():
        return []
    records = []
    with open(trace_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(ToolCallRecord.model_validate_json(line))
    return records


def verify_trace(sample_dir: Path) -> list[str]:
    """Post-hoc verification: check that recorded field values appear in page text.

    Returns a list of warnings for values that could not be found in any
    read_page_text or query_selector_text output in the trace.
    """
    records = load_agent_trace(sample_dir)

    # Collect all text observed from the page
    observed_texts: list[str] = []
    for r in records:
        if r.tool_name == "read_page_text":
            text = r.output.get("text", "")
            if text:
                observed_texts.append(text)
        elif r.tool_name == "query_selector_text":
            text = r.output.get("text", "")
            if text:
                observed_texts.append(text)
        elif r.tool_name == "query_selector_all_text":
            for item in r.output.get("items", []):
                text = item.get("text", "")
                if text:
                    observed_texts.append(text)

    combined_text = "\n".join(observed_texts)

    # Check each recorded field value against observed text
    warnings: list[str] = []
    for r in records:
        if r.tool_name == "record_field":
            field_name = r.input.get("field_name", "")
            value = r.input.get("value", "")
            if value and value not in combined_text:
                warnings.append(
                    f"Field '{field_name}' value '{value}' not found in any observed page text"
                )

    return warnings
