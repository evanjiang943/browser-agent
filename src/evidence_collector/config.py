"""Configuration schema and loading."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class BrowserConfig(BaseModel):
    """Browser automation settings."""

    headless: bool = True
    timeout_ms: int = 30_000
    profile_dir: str | None = None


class ThrottleConfig(BaseModel):
    """Rate limiting settings."""

    max_pages_per_minute: int = 20
    retry_attempts: int = 3
    backoff_base_seconds: float = 2.0


class ScreenshotConfig(BaseModel):
    """Screenshot capture settings."""

    mode: str = "viewport"  # viewport | tiled | full_page
    quality: int = 90


class RunConfig(BaseModel):
    """Top-level run configuration."""

    browser: BrowserConfig = BrowserConfig()
    throttle: ThrottleConfig = ThrottleConfig()
    screenshot: ScreenshotConfig = ScreenshotConfig()
    concurrency: int = 1


def load_config(path: str | None = None) -> RunConfig:
    """Load configuration from a file, falling back to defaults.

    - ``path=None`` → return ``RunConfig()`` (all defaults).
    - ``.json`` file → parse JSON and validate.
    - Other extensions → attempt YAML via PyYAML (optional dependency).
    - Missing file → ``FileNotFoundError``.
    """
    if path is None:
        return RunConfig()

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    text = p.read_text()

    if p.suffix == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required to load YAML config files. "
                "Install it with: pip install pyyaml"
            ) from exc
        data = yaml.safe_load(text)

    return RunConfig.model_validate(data)
