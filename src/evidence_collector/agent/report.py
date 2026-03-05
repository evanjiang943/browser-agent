"""Markdown report generation for audit evidence."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from evidence_collector.agent.audit import ToolCallRecord, load_agent_trace
from evidence_collector.io.paths import read_notes
from evidence_collector.web.progress import tool_progress_message


def generate_sample_report(sample_dir: Path) -> Path:
    """Generate a markdown report for a single sample.

    Reads the agent trace, notes, and screenshots from sample_dir and writes
    a report.md summarizing what the agent did with inline screenshot references.

    Returns the path to the generated report.
    """
    notes = read_notes(sample_dir) or {}
    records = load_agent_trace(sample_dir)
    sample_id = notes.get("sample_id", sample_dir.name)
    status = notes.get("status", "unknown")
    result_data = notes.get("result_data", {})

    lines: list[str] = []
    lines.append(f"# Sample: {sample_id}\n")
    lines.append(f"**Status:** {status}\n")

    # Collected data summary
    if result_data:
        lines.append("## Collected Data\n")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        for k, v in result_data.items():
            v_escaped = str(v).replace("|", "\\|")
            lines.append(f"| {k} | {v_escaped} |")
        lines.append("")

    # Agent walkthrough
    if records:
        lines.append("## Agent Walkthrough\n")
        screenshot_idx = 0
        for r in records:
            msg = tool_progress_message(r.tool_name, r.input)

            if r.tool_name == "take_screenshot":
                screenshot_idx += 1
                label = r.input.get("label", f"screenshot_{screenshot_idx}")
                # Find the actual screenshot file
                ss_file = _find_screenshot(sample_dir, label, screenshot_idx)
                if ss_file:
                    rel = ss_file.relative_to(sample_dir)
                    lines.append(f"**{msg}**\n")
                    lines.append(f"![{label}]({rel})\n")
                else:
                    lines.append(f"- {msg}\n")

            elif r.tool_name == "record_field":
                field_name = r.input.get("field_name", "")
                value = r.input.get("value", "")
                lines.append(f"- **Recorded `{field_name}`** = {value}\n")

            elif r.tool_name == "open_url":
                url = r.input.get("url", "")
                lines.append(f"- Navigated to [{url}]({url})\n")

            elif r.tool_name in ("read_page_text", "query_selector_text", "query_selector_all_text"):
                # Skip verbose read operations, they clutter the report
                pass

            elif r.tool_name in ("get_required_fields", "get_recorded_fields"):
                # Skip internal state queries
                pass

            else:
                lines.append(f"- {msg}\n")

    # Errors
    errors = notes.get("errors", [])
    if errors:
        lines.append("## Errors\n")
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")

    content = "\n".join(lines)
    dest = sample_dir / "report.md"
    fd, tmp_path = tempfile.mkstemp(dir=sample_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, dest)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return dest


def generate_run_report(out_dir: Path, task_name: str) -> Path:
    """Generate a top-level markdown report summarizing the entire run.

    Compiles per-sample reports into a single document with a summary table
    and inline screenshots.

    Returns the path to the generated report.
    """
    evidence_dir = out_dir / "evidence" / task_name
    lines: list[str] = []
    lines.append(f"# Evidence Collection Report: {task_name}\n")

    # Collect all sample dirs
    sample_dirs = sorted(
        [d for d in evidence_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    ) if evidence_dir.exists() else []

    if not sample_dirs:
        lines.append("No samples processed.\n")
        content = "\n".join(lines)
        dest = out_dir / "report.md"
        dest.write_text(content)
        return dest

    # Summary table
    lines.append("## Summary\n")
    lines.append("| # | Sample | Status | Fields Collected |")
    lines.append("|---|--------|--------|-----------------|")

    sample_notes_list = []
    for i, sd in enumerate(sample_dirs):
        notes = read_notes(sd) or {}
        sample_notes_list.append((sd, notes))
        sid = notes.get("sample_id", sd.name)
        status = notes.get("status", "unknown")
        field_count = len(notes.get("result_data", {}))
        lines.append(f"| {i + 1} | {sid} | {status} | {field_count} |")
    lines.append("")

    # Per-sample detail sections
    for sd, notes in sample_notes_list:
        sid = notes.get("sample_id", sd.name)
        status = notes.get("status", "unknown")
        result_data = notes.get("result_data", {})
        records = load_agent_trace(sd)

        lines.append(f"---\n")
        lines.append(f"## {sid}\n")
        lines.append(f"**Status:** {status}\n")

        # Collected data
        if result_data:
            lines.append("### Collected Data\n")
            lines.append("| Field | Value |")
            lines.append("|-------|-------|")
            for k, v in result_data.items():
                v_escaped = str(v).replace("|", "\\|")
                lines.append(f"| {k} | {v_escaped} |")
            lines.append("")

        # Key actions with screenshots
        if records:
            lines.append("### Agent Actions\n")
            screenshot_idx = 0
            for r in records:
                msg = tool_progress_message(r.tool_name, r.input)

                if r.tool_name == "take_screenshot":
                    screenshot_idx += 1
                    label = r.input.get("label", f"screenshot_{screenshot_idx}")
                    ss_file = _find_screenshot(sd, label, screenshot_idx)
                    if ss_file:
                        rel = ss_file.relative_to(out_dir)
                        lines.append(f"**{msg}**\n")
                        lines.append(f"![{label}]({rel})\n")
                    else:
                        lines.append(f"- {msg}\n")

                elif r.tool_name == "record_field":
                    field_name = r.input.get("field_name", "")
                    value = r.input.get("value", "")
                    lines.append(f"- **Recorded `{field_name}`** = {value}\n")

                elif r.tool_name == "open_url":
                    url = r.input.get("url", "")
                    lines.append(f"- Navigated to [{url}]({url})\n")

                elif r.tool_name in (
                    "read_page_text", "query_selector_text",
                    "query_selector_all_text", "get_required_fields",
                    "get_recorded_fields",
                ):
                    pass

                else:
                    lines.append(f"- {msg}\n")

        # Errors
        errors = notes.get("errors", [])
        if errors:
            lines.append("### Errors\n")
            for e in errors:
                lines.append(f"- {e}")
            lines.append("")

    content = "\n".join(lines)
    dest = out_dir / "report.md"
    fd, tmp_path = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, dest)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return dest


def _find_screenshot(sample_dir: Path, label: str, index: int) -> Path | None:
    """Find a screenshot file by label or index in the sample's screenshots dir."""
    ss_dir = sample_dir / "screenshots"
    if not ss_dir.exists():
        return None

    # Try exact label match first
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = ss_dir / f"{label}{ext}"
        if candidate.exists():
            return candidate

    # Try label as substring
    for f in sorted(ss_dir.iterdir()):
        if label.replace(" ", "_").lower() in f.name.lower():
            return f

    # Fall back to index-based
    files = sorted(f for f in ss_dir.iterdir() if f.is_file())
    if 0 < index <= len(files):
        return files[index - 1]

    return None
