"""Core browser adapter — wraps Playwright for page navigation and interaction.

Usage in a playbook runner::

    adapter = BrowserAdapter(profile_dir=Path("~/.chrome-profile"), headless=True)
    page = await adapter.open("https://github.com/org/repo")
    await adapter.screenshot(page, Path("evidence/shot.png"))
    await adapter.close()
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import aiohttp
from playwright.async_api import Page, async_playwright

logger = logging.getLogger(__name__)


# ── Generic extraction primitives ───────────────────────────────────────


@dataclass
class ExtractionRule:
    """Declarative rule for extracting a single field from a page.

    *selectors* are tried in order; the text content of the first match wins.
    If all selectors miss, *fallback_pattern* (a regex) is applied to the
    visible page text.  *transform* post-processes the extracted string.
    If *required* is True, a warning is logged on miss (but no exception).
    """

    field: str
    selectors: list[str] = field(default_factory=list)
    fallback_pattern: str | None = None
    transform: Callable[[str], str] | None = None
    required: bool = False


async def extract_fields(page: Page, rules: list[ExtractionRule]) -> dict[str, str]:
    """Extract multiple fields from *page* according to *rules*.

    Returns ``{rule.field: value}`` for every rule.  Missing fields
    are returned as empty strings.
    """
    body_text: str | None = None  # lazy — only fetched if a fallback needs it
    result: dict[str, str] = {}

    for rule in rules:
        value = ""

        # 1. Try each CSS selector in order
        for selector in rule.selectors:
            el = await page.query_selector(selector)
            if el is not None:
                value = (await el.inner_text()).strip()
                if value:
                    break

        # 2. Fallback to regex on visible text
        if not value and rule.fallback_pattern is not None:
            if body_text is None:
                body_text = await page.inner_text("body")
            m = re.search(rule.fallback_pattern, body_text)
            if m:
                value = m.group(1) if m.lastindex else m.group(0)
                value = value.strip()

        # 3. Log if required and still missing
        if not value and rule.required:
            logger.warning("Required field %r not found on page", rule.field)

        # 4. Apply transform
        if value and rule.transform is not None:
            value = rule.transform(value)

        result[rule.field] = value

    return result


async def find_links_matching(page: Page, patterns: list[str]) -> list[str]:
    """Return deduplicated hrefs matching any of *patterns* (regexes).

    Links are returned in DOM order, deduplicated by first occurrence.
    """
    elements = await page.query_selector_all("a[href]")
    compiled = [re.compile(p) for p in patterns]
    seen: set[str] = set()
    matched: list[str] = []

    for el in elements:
        href = await el.get_attribute("href")
        if not href or href in seen:
            continue
        for pat in compiled:
            if pat.search(href):
                seen.add(href)
                matched.append(href)
                break

    return matched


async def verify_url(
    url: str, session: aiohttp.ClientSession
) -> dict[str, Any]:
    """Verify that *url* is reachable via HEAD (fallback GET).

    Returns::

        {"url": ..., "status_code": ..., "alive": bool,
         "redirect_url": str | None, "error": str | None}

    Timeout is 10 s.  No retries — the caller is responsible.
    """
    timeout = aiohttp.ClientTimeout(total=10)
    redirect_url: str | None = None
    try:
        async with session.head(
            url, allow_redirects=True, timeout=timeout
        ) as resp:
            status = resp.status
            if str(resp.url) != url:
                redirect_url = str(resp.url)
            # Retry with GET if HEAD returns 405 Method Not Allowed
            if status == 405:
                async with session.get(
                    url, allow_redirects=True, timeout=timeout
                ) as resp2:
                    status = resp2.status
                    if str(resp2.url) != url:
                        redirect_url = str(resp2.url)
    except Exception as exc:
        return {
            "url": url,
            "status_code": None,
            "alive": False,
            "redirect_url": None,
            "error": str(exc),
        }

    return {
        "url": url,
        "status_code": status,
        "alive": 200 <= status < 400,
        "redirect_url": redirect_url,
        "error": None,
    }


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
        error_screenshot_dir: Path | None = None,
    ) -> None:
        self.profile_dir = profile_dir
        self.headless = headless
        self.timeout = timeout
        self.error_screenshot_dir = error_screenshot_dir
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

    async def _capture_error_screenshot(self, page: Page, label: str) -> None:
        """Best-effort screenshot on error, saved to error_screenshot_dir."""
        if self.error_screenshot_dir is None:
            return
        try:
            self.error_screenshot_dir.mkdir(parents=True, exist_ok=True)
            dest = self.error_screenshot_dir / f"{label}.png"
            await page.screenshot(path=str(dest))
            logger.info("Error screenshot saved: %s", dest)
        except Exception:
            logger.warning("Failed to capture error screenshot", exc_info=True)

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
            await self._capture_error_screenshot(page, "login_redirect")
            raise LoginRedirectError(
                f"Redirected to login page: {page.url} (requested {url})"
            )

        # 404 detection
        title = await page.title()
        if re.search(r"404|not\s*found", title, re.IGNORECASE):
            await self._capture_error_screenshot(page, "page_not_found")
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
            vp = page.viewport_size
            if vp is None:
                raise RuntimeError(
                    "Cannot take tiled screenshot: viewport size is not set"
                )
            viewport_height = vp["height"]
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
