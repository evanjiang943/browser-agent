"""Ticket screenshots + CSV extraction playbook runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseRunner


class TicketsRunner(BaseRunner):
    """Playbook A: open ticket URLs, screenshot, extract fields."""

    def load_samples(self) -> list[dict]:
        # TODO: read CSV/XLSX, validate 'url' column exists
        raise NotImplementedError

    def process_sample(self, sample: dict) -> dict:
        # TODO: open URL, wait for ticket header, extract ticket_id/assignee/due_date,
        #       take screenshots (header + details), write notes.json
        raise NotImplementedError
