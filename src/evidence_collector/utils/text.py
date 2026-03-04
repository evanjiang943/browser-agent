"""Text processing and extraction helpers."""

from __future__ import annotations

import re


def extract_jira_urls(text: str) -> list[str]:
    """Find Jira ticket URLs in text."""
    # TODO: regex match common Jira URL patterns
    raise NotImplementedError


def extract_linear_urls(text: str) -> list[str]:
    """Find Linear ticket URLs in text."""
    # TODO: regex match Linear URL patterns
    raise NotImplementedError


def extract_ticket_id(url: str) -> str | None:
    """Extract a ticket identifier from a URL."""
    # TODO: parse URL path to find ticket ID segment
    raise NotImplementedError


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace and strip a string."""
    # TODO: replace multiple whitespace chars with single space, strip
    raise NotImplementedError
