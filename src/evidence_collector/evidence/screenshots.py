"""Screenshot capture and storage utilities."""

from __future__ import annotations

from pathlib import Path


def capture_viewport(page, output_path: Path) -> Path:
    """Capture a viewport screenshot."""
    # TODO: take viewport screenshot via Playwright page, save to output_path
    raise NotImplementedError


def capture_full_page(page, output_path: Path) -> Path:
    """Capture a full-page screenshot."""
    # TODO: take full-page screenshot, save to output_path
    raise NotImplementedError


def capture_tiled(page, output_dir: Path, prefix: str) -> list[Path]:
    """Capture tiled scroll screenshots for long pages."""
    # TODO: scroll page in viewport-sized increments, capture each tile,
    #       save with sequential numbering
    raise NotImplementedError
