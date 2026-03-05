"""WebSocket message router: dispatches chat/upload/confirm/cancel."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from evidence_collector.agent.runner import AgentRunner
from evidence_collector.agent.task import TaskDescription
from evidence_collector.config import RunConfig
from evidence_collector.io.spreadsheets import read_input
from evidence_collector.web.chat_planner import ChatPlannerResult, chat_planner_turn
from evidence_collector.web.progress import ProgressEvent, tool_progress_message
from evidence_collector.web.session import Session, SessionManager

logger = logging.getLogger(__name__)


async def handle_websocket(ws: Any, sessions: SessionManager, upload_dir: Path, output_base: Path) -> None:
    """Handle a single WebSocket connection lifecycle."""
    session = sessions.create()

    await _send(ws, {
        "type": "chat",
        "role": "assistant",
        "text": (
            "Hello! I'm the evidence collection agent. "
            "Upload a CSV/XLSX file and describe what evidence you'd like me to collect. "
            "I'll ask clarifying questions, then get to work."
        ),
    })

    try:
        async for raw in ws.iter_text():
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send(ws, {"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")
            try:
                if msg_type == "chat":
                    await _handle_chat(ws, session, msg)
                elif msg_type == "upload_done":
                    await _handle_upload(ws, session, msg, upload_dir)
                elif msg_type == "confirm_task":
                    await _handle_confirm(ws, session, output_base)
                elif msg_type == "cancel":
                    await _handle_cancel(ws, session)
                else:
                    await _send(ws, {"type": "error", "message": f"Unknown message type: {msg_type}"})
            except Exception as exc:
                logger.exception("Error handling message type=%s", msg_type)
                await _send(ws, {"type": "error", "message": str(exc)})
    finally:
        sessions.remove(session.session_id)


async def _handle_chat(ws: Any, session: Session, msg: dict) -> None:
    """Handle a chat message from the user."""
    user_text = msg.get("text", "").strip()
    if not user_text:
        return

    if session.phase == "done":
        await _send(ws, {
            "type": "chat",
            "role": "assistant",
            "text": "The run is complete. You can download the results above, or refresh the page to start a new session.",
        })
        return

    if session.phase == "running":
        await _send(ws, {
            "type": "chat",
            "role": "assistant",
            "text": "The agent is currently running. You can cancel it or wait for it to finish.",
        })
        return

    # Phase: chat — run planner turn
    sample_row = session.sample_rows[0] if session.sample_rows else None
    result: ChatPlannerResult = await chat_planner_turn(
        messages=session.messages,
        user_text=user_text,
        sample_row=sample_row if not session.messages else None,  # Only on first turn
    )

    if result.text:
        await _send(ws, {"type": "chat", "role": "assistant", "text": result.text})

    if result.task:
        session.task = result.task
        await _send(ws, {
            "type": "task_preview",
            "task": result.task.model_dump(),
        })


async def _handle_upload(ws: Any, session: Session, msg: dict, upload_dir: Path) -> None:
    """Handle file upload completion."""
    file_path = upload_dir / msg.get("file_id", "")
    if not file_path.exists():
        await _send(ws, {"type": "error", "message": "Uploaded file not found"})
        return

    try:
        rows = read_input(file_path)
    except Exception as exc:
        await _send(ws, {"type": "error", "message": f"Could not read file: {exc}"})
        return

    session.uploaded_file = file_path
    session.sample_rows = rows

    columns = list(rows[0].keys()) if rows else []
    await _send(ws, {
        "type": "columns_detected",
        "columns": columns,
        "row_count": len(rows),
        "filename": msg.get("filename", file_path.name),
    })


async def _handle_confirm(ws: Any, session: Session, output_base: Path) -> None:
    """Handle task confirmation — start the agent run."""
    if not session.task:
        await _send(ws, {"type": "error", "message": "No task to confirm"})
        return
    if not session.uploaded_file:
        await _send(ws, {"type": "error", "message": "No file uploaded"})
        return

    approved = True  # confirm_task message means approval
    if not approved:
        return

    session.phase = "running"
    session.output_dir = output_base / session.session_id

    total_samples = len(session.sample_rows) if session.sample_rows else 0

    await _send(ws, {
        "type": "chat",
        "role": "assistant",
        "text": "Starting the evidence collection run...",
    })

    await _send(ws, {
        "type": "run_started",
        "total_samples": total_samples,
    })

    # Create progress queue and callback
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def on_progress(event: dict) -> None:
        await queue.put(event)

    runner = AgentRunner(
        task=session.task,
        input_path=session.uploaded_file,
        output_dir=session.output_dir,
        config=RunConfig(browser=RunConfig().browser),
        on_progress=on_progress,
    )

    async def _run_and_signal() -> None:
        try:
            await runner._run_async()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            await queue.put({"event_type": "error", "message": str(exc)})
        finally:
            await queue.put(None)  # Sentinel

    session.run_task = asyncio.create_task(_run_and_signal())

    # Stream progress events to the WebSocket
    while True:
        event = await queue.get()
        if event is None:
            break

        event_type = event.get("event_type", "")

        if event_type == "tool_call":
            message = tool_progress_message(
                event.get("tool_name", ""),
                event.get("tool_params", {}),
            )
            await _send(ws, {
                "type": "progress",
                "event_type": "tool_call",
                "sample_id": event.get("sample_id", ""),
                "message": message,
            })

        elif event_type == "sample_start":
            await _send(ws, {
                "type": "progress",
                "event_type": "sample_start",
                "sample_id": event.get("sample_id", ""),
                "sample_index": event.get("sample_index", 0),
                "total": event.get("total_samples", 0),
                "message": f"Starting sample {event.get('sample_index', 0) + 1}/{event.get('total_samples', 0)}: {event.get('sample_id', '')}",
            })

        elif event_type == "sample_end":
            await _send(ws, {
                "type": "progress",
                "event_type": "sample_end",
                "sample_id": event.get("sample_id", ""),
                "sample_index": event.get("sample_index", 0),
                "total": event.get("total_samples", 0),
                "status": event.get("status", ""),
                "message": f"Completed sample {event.get('sample_index', 0) + 1}/{event.get('total_samples', 0)}: {event.get('status', '')}",
            })

        elif event_type == "error":
            await _send(ws, {"type": "error", "message": event.get("message", "Unknown error")})

    # Run complete
    session.phase = "done"

    # Collect output summary
    summary = _collect_output_summary(session)

    await _send(ws, {"type": "execution_complete", "summary": {"phase": "done"}})
    await _send(ws, {"type": "download_ready", **summary})


async def _handle_cancel(ws: Any, session: Session) -> None:
    """Cancel a running agent."""
    if session.run_task and not session.run_task.done():
        session.run_task.cancel()
        session.phase = "done"
        await _send(ws, {
            "type": "chat",
            "role": "assistant",
            "text": "Run cancelled.",
        })
    else:
        await _send(ws, {
            "type": "chat",
            "role": "assistant",
            "text": "Nothing to cancel.",
        })


def _collect_output_summary(session: Session) -> dict:
    """Gather categorized output info for the download_ready message."""
    result: dict = {
        "session_id": session.session_id,
        "zip_url": f"/api/download/{session.session_id}",
        "results_csv": None,
        "sample_count": 0,
        "screenshot_count": 0,
        "download_count": 0,
        "trace_count": 0,
        "top_files": [],
    }
    if not session.output_dir or not session.output_dir.exists():
        return result

    csv_path = session.output_dir / "results.csv"
    if csv_path.exists():
        result["results_csv"] = {
            "name": "results.csv",
            "url": f"/api/files/{session.session_id}/results.csv",
        }

    evidence_dir = None
    for d in session.output_dir.iterdir():
        if d.is_dir() and d.name == "evidence":
            evidence_dir = d
            break

    if evidence_dir:
        for task_dir in evidence_dir.iterdir():
            if not task_dir.is_dir():
                continue
            for sample_dir in task_dir.iterdir():
                if not sample_dir.is_dir():
                    continue
                result["sample_count"] += 1
                ss_dir = sample_dir / "screenshots"
                if ss_dir.exists():
                    result["screenshot_count"] += len(list(ss_dir.iterdir()))
                dl_dir = sample_dir / "downloads"
                if dl_dir.exists():
                    result["download_count"] += len(list(dl_dir.iterdir()))
                if (sample_dir / "agent_trace.jsonl").exists():
                    result["trace_count"] += 1

    # Top-level files for quick access links
    for name in ["results.csv", "run_manifest.json", "run_log.jsonl"]:
        p = session.output_dir / name
        if p.exists():
            result["top_files"].append({
                "name": name,
                "url": f"/api/files/{session.session_id}/{name}",
            })

    return result


async def _send(ws: Any, data: dict) -> None:
    """Send a JSON message over the WebSocket."""
    try:
        await ws.send_text(json.dumps(data))
    except Exception:
        pass
