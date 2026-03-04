"""Jira/Linear adapter — ticket system interactions."""

from __future__ import annotations


class JiraLikeAdapter:
    """Adapter for Jira, Linear, and similar ticket systems."""

    def __init__(self, browser_adapter) -> None:
        self.browser = browser_adapter

    async def open_ticket(self, url: str) -> None:
        """Open a ticket page."""
        # TODO: navigate to ticket URL, wait for ticket content to load
        raise NotImplementedError

    async def extract_ticket_fields(self) -> dict:
        """Extract ticket_id, assignee, due_date, status from current page."""
        # TODO: extract fields using selectors with text heuristic fallback
        raise NotImplementedError

    async def detect_ticket_system(self, url: str) -> str:
        """Detect which ticket system a URL belongs to (jira, linear, etc.)."""
        # TODO: pattern match URL to determine system type
        raise NotImplementedError
