"""Core browser adapter — wraps Playwright for page navigation and interaction."""

from __future__ import annotations

from pathlib import Path


class BrowserAdapter:
    """Low-level browser operations: open pages, click, wait, screenshot, download."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self._browser = None
        self._context = None
        self._page = None

    async def launch(self) -> None:
        """Launch browser instance."""
        # TODO: launch Playwright browser with config (headless, profile, etc.)
        raise NotImplementedError

    async def close(self) -> None:
        """Close browser instance."""
        # TODO: close browser and cleanup
        raise NotImplementedError

    async def goto(self, url: str) -> None:
        """Navigate to URL and wait for page readiness."""
        # TODO: navigate, wait for network idle or DOM ready
        raise NotImplementedError

    async def screenshot(self, path: Path, full_page: bool = False) -> Path:
        """Take a screenshot and save to path."""
        # TODO: capture screenshot with configured mode (viewport/full_page)
        raise NotImplementedError

    async def screenshot_tiled(self, base_path: Path) -> list[Path]:
        """Take tiled scroll-capture screenshots for long pages."""
        # TODO: scroll and capture each viewport segment
        raise NotImplementedError

    async def download_file(self, download_dir: Path) -> Path | None:
        """Wait for and save a triggered download."""
        # TODO: handle download event, save to download_dir
        raise NotImplementedError

    async def extract_text(self, selector: str) -> str | None:
        """Extract text content from a selector."""
        # TODO: query selector, return text content or None
        raise NotImplementedError

    async def click(self, selector: str) -> None:
        """Click an element."""
        # TODO: find element by selector and click
        raise NotImplementedError

    async def fill(self, selector: str, value: str) -> None:
        """Fill a form field."""
        # TODO: find input by selector and fill with value
        raise NotImplementedError

    async def wait_for_selector(self, selector: str, timeout_ms: int | None = None) -> bool:
        """Wait for a selector to appear on the page."""
        # TODO: wait for element, return True if found, False on timeout
        raise NotImplementedError

    async def detect_login_redirect(self) -> bool:
        """Detect if the page redirected to a login/SSO page."""
        # TODO: check URL patterns and page content for login indicators
        raise NotImplementedError
