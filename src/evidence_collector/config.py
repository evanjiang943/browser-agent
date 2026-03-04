"""Configuration schema and loading."""

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
    """Load configuration from YAML file, falling back to defaults."""
    # TODO: load from YAML file if path provided, merge with defaults
    raise NotImplementedError
