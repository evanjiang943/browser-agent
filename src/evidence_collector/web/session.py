"""Session management for web UI connections."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evidence_collector.agent.task import TaskDescription


@dataclass
class Session:
    """State for a single WebSocket connection."""

    session_id: str
    phase: str = "chat"  # chat | running | done
    messages: list[dict[str, Any]] = field(default_factory=list)
    uploaded_file: Path | None = None
    sample_rows: list[dict] | None = None
    task: TaskDescription | None = None
    output_dir: Path | None = None
    run_task: asyncio.Task | None = None


class SessionManager:
    """In-memory session store (single-user tool, no persistence needed)."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        session_id = uuid.uuid4().hex[:12]
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session and session.run_task and not session.run_task.done():
            session.run_task.cancel()
