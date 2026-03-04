"""Text processing and extraction helpers."""

from __future__ import annotations

import re
from urllib.parse import urlparse


def extract_jira_urls(text: str) -> list[str]:
    """Find Jira ticket URLs in text."""
    return re.findall(r"https?://[^\s/]+/browse/[A-Z][A-Z0-9]+-\d+", text)


def extract_linear_urls(text: str) -> list[str]:
    """Find Linear ticket URLs in text."""
    return re.findall(
        r"https?://linear\.app/[a-zA-Z0-9_-]+/issue/[A-Z][A-Z0-9]+-\d+", text
    )


def extract_ticket_id(url: str) -> str | None:
    """Extract a ticket identifier from a URL.

    Looks for KEY-123 pattern in the URL path. Falls back to the last
    non-empty path segment if no ticket pattern is found.
    """
    parsed = urlparse(url)
    path = parsed.path
    match = re.search(r"[A-Z][A-Z0-9]+-\d+", path)
    if match:
        return match.group(0)
    segments = [s for s in path.split("/") if s]
    return segments[-1] if segments else None


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace and strip a string."""
    return re.sub(r"\s+", " ", text).strip()
