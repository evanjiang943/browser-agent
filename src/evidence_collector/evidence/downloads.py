"""Download handling and storage."""

from __future__ import annotations

from pathlib import Path


def save_download(download, target_dir: Path) -> Path:
    """Save a Playwright download to the target directory."""
    # TODO: wait for download, save to target_dir with original filename
    raise NotImplementedError


def organize_downloads(download_dir: Path) -> list[Path]:
    """List and validate downloaded files in a directory."""
    # TODO: list files, verify non-empty, return paths
    raise NotImplementedError
