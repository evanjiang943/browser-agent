"""Evidence naming conventions and sample ID generation."""

from __future__ import annotations

import hashlib
import re

from evidence_collector.utils.time import now_filename_stamp


def generate_sample_id(primary_key: str | None = None, url: str | None = None, name: str | None = None) -> str:
    """Generate a deterministic sample ID from a primary key, URL, or name.

    Priority: primary_key > url > name. Falls back to hashing for stability.
    """
    if primary_key:
        slug = re.sub(r"[^a-z0-9]", "-", primary_key.lower())
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")
        return slug
    elif url:
        return hashlib.sha256(url.encode()).hexdigest()[:12]
    elif name:
        return hashlib.sha256(name.encode()).hexdigest()[:12]
    else:
        raise ValueError("At least one of primary_key, url, or name must be provided")


def screenshot_filename(sample_id: str, system: str, step: str, index: int = 0) -> str:
    """Generate a screenshot filename following the naming convention.

    Format: <sample_id>__<system>__<step>__<YYYYMMDD-HHMMSS>__<n>.png
    """
    timestamp = now_filename_stamp()
    return f"{sample_id}__{system}__{step}__{timestamp}__{index}.png"


def safe_folder_name(raw: str) -> str:
    """Sanitize a string for use as a folder name."""
    sanitized = re.sub(r'[/\\:*?"<>|\s]', "-", raw)
    sanitized = re.sub(r"-+", "-", sanitized)
    sanitized = sanitized.strip("-")
    return sanitized if sanitized else "_unnamed"
