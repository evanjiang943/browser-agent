"""Core browser adapter — wraps Playwright for page navigation and interaction.

Usage in a playbook runner::

    adapter = BrowserAdapter(profile_dir=Path("~/.chrome-profile"), headless=True)
    page = await adapter.open("https://github.com/org/repo")
    await adapter.screenshot(page, Path("evidence/shot.png"))
    await adapter.close()
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Page, async_playwright


class LoginRedirectError(Exception):
    """Raised when navigation results in a redirect to a login/SSO page."""


class PageNotFoundError(Exception):
    """Raised when the target page returns a 404 or not-found response."""


class BrowserAdapter:
    """Drives a Playwright Chromium browser for evidence collection."""

    def __init__(
        self,
        profile_dir: Path | None = None,
        headless: bool = False,
        timeout: int = 30_000,
    ) -> None:
        self.profile_dir = profile_dir
        self.headless = headless
        self.timeout = timeout
        self._playwright = None
        self._browser = None
        self._context = None

    async def _ensure_browser(self) -> None:
        """Lazily launch browser on first use."""
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        if self.profile_dir is not None:
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
            )
            self._browser = self._context.browser
        else:
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
            )
            self._context = await self._browser.new_context()

    async def open(self, url: str) -> Page:
        """Navigate to *url* and return the Playwright Page.

        Raises LoginRedirectError if the page redirected to a login page.
        Raises PageNotFoundError if the resulting page looks like a 404.
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        await page.goto(url, wait_until="networkidle", timeout=self.timeout)

        # Login redirect detection
        requested = urlparse(url)
        actual = urlparse(page.url)
        if actual.netloc != requested.netloc or re.search(
            r"login|signin", actual.path, re.IGNORECASE
        ):
            raise LoginRedirectError(
                f"Redirected to login page: {page.url} (requested {url})"
            )

        # 404 detection
        title = await page.title()
        if re.search(r"404|not\s*found", title, re.IGNORECASE):
            raise PageNotFoundError(f"Page not found: {url} (title: {title!r})")

        return page

    async def screenshot(
        self, page: Page, path: Path, mode: str = "viewport"
    ) -> None:
        """Capture a screenshot of *page*.

        mode="viewport": single screenshot of the current viewport.
        mode="tiled": scroll in viewport-height increments, saving numbered tiles.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "viewport":
            await page.screenshot(path=str(path))
        elif mode == "tiled":
            scroll_height = await page.evaluate("document.body.scrollHeight")
            viewport_height = page.viewport_size["height"]
            tiles = max(1, -(-scroll_height // viewport_height))  # ceil division
            for i in range(tiles):
                await page.evaluate(f"window.scrollTo(0, {i * viewport_height})")
                await page.wait_for_timeout(200)  # let rendering settle
                tile_path = path.with_name(f"{path.stem}_{i}{path.suffix}")
                await page.screenshot(path=str(tile_path))
        else:
            raise ValueError(f"Unknown screenshot mode: {mode!r}")

    async def download_file(
        self, page: Page, selector: str, dest: Path
    ) -> Path:
        """Click *selector* to trigger a download and save it to *dest*."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with page.expect_download() as download_info:
            await page.click(selector)
        download = await download_info.value
        await download.save_as(str(dest))
        return dest

    async def close(self) -> None:
        """Close browser and stop Playwright."""
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
