"""Evidence naming conventions and sample ID generation."""

from __future__ import annotations

import hashlib


def generate_sample_id(primary_key: str | None = None, url: str | None = None, name: str | None = None) -> str:
    """Generate a deterministic sample ID from a primary key, URL, or name.

    Priority: primary_key > url > name. Falls back to hashing for stability.
    """
    # TODO: use primary_key directly if available (sanitized),
    #       else hash URL or name for a stable, filesystem-safe ID
    raise NotImplementedError


def screenshot_filename(sample_id: str, system: str, step: str, index: int = 0) -> str:
    """Generate a screenshot filename following the naming convention.

    Format: <sample_id>__<system>__<step>__<YYYYMMDD-HHMMSS>__<n>.png
    """
    # TODO: build filename with timestamp and sequential index
    raise NotImplementedError


def safe_folder_name(raw: str) -> str:
    """Sanitize a string for use as a folder name."""
    # TODO: remove/replace unsafe filesystem characters
    raise NotImplementedError
