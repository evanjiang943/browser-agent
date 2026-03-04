"""Tests for evidence_collector.adapters.browser (BrowserAdapter).

All Playwright objects are mocked — no real browser is launched.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from evidence_collector.adapters.browser import (
    BrowserAdapter,
    LoginRedirectError,
    PageNotFoundError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_page(
    url: str = "https://example.com/page",
    title: str = "Example Page",
    viewport_size: dict | None = None,
) -> AsyncMock:
    """Return a mock Playwright Page with sensible defaults."""
    page = AsyncMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    # viewport_size is a property (not a coroutine)
    type(page).viewport_size = PropertyMock(
        return_value=viewport_size or {"width": 1280, "height": 720}
    )
    page.goto = AsyncMock()
    page.screenshot = AsyncMock()
    page.evaluate = AsyncMock(return_value=1440)  # default scroll_height
    page.wait_for_timeout = AsyncMock()
    page.click = AsyncMock()
    return page


def _make_adapter(**kwargs) -> BrowserAdapter:
    """Create a BrowserAdapter and stub out _ensure_browser + context."""
    adapter = BrowserAdapter(**kwargs)
    # Pre-set internals so _ensure_browser is already satisfied
    adapter._playwright = MagicMock()
    adapter._browser = MagicMock()
    context = AsyncMock()
    adapter._context = context
    return adapter


# ---------------------------------------------------------------------------
# open() — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_success():
    adapter = _make_adapter()
    page = _make_page(url="https://example.com/page")
    adapter._context.new_page = AsyncMock(return_value=page)

    result = await adapter.open("https://example.com/page")
    assert result is page
    page.goto.assert_awaited_once()


# ---------------------------------------------------------------------------
# open() — login redirect (netloc mismatch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_login_redirect_netloc():
    adapter = _make_adapter()
    page = _make_page(url="https://sso.example.com/login?next=/page")
    adapter._context.new_page = AsyncMock(return_value=page)

    with pytest.raises(LoginRedirectError, match="Redirected to login"):
        await adapter.open("https://example.com/page")


# ---------------------------------------------------------------------------
# open() — login redirect (path contains "login")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_login_redirect_path():
    adapter = _make_adapter()
    page = _make_page(url="https://example.com/login?next=/page")
    adapter._context.new_page = AsyncMock(return_value=page)

    with pytest.raises(LoginRedirectError, match="Redirected to login"):
        await adapter.open("https://example.com/page")


# ---------------------------------------------------------------------------
# open() — 404 (title contains "404")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_404_title_number():
    adapter = _make_adapter()
    page = _make_page(url="https://example.com/page", title="Error 404")
    adapter._context.new_page = AsyncMock(return_value=page)

    with pytest.raises(PageNotFoundError, match="Page not found"):
        await adapter.open("https://example.com/page")


# ---------------------------------------------------------------------------
# open() — 404 (title contains "Not Found")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_404_title_not_found():
    adapter = _make_adapter()
    page = _make_page(url="https://example.com/page", title="Page Not Found")
    adapter._context.new_page = AsyncMock(return_value=page)

    with pytest.raises(PageNotFoundError, match="Page not found"):
        await adapter.open("https://example.com/page")


# ---------------------------------------------------------------------------
# open() — error screenshot captured before raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_error_screenshot_captured(tmp_path):
    adapter = _make_adapter(error_screenshot_dir=tmp_path / "errors")
    page = _make_page(url="https://sso.example.com/login")
    adapter._context.new_page = AsyncMock(return_value=page)

    with pytest.raises(LoginRedirectError):
        await adapter.open("https://example.com/page")

    page.screenshot.assert_awaited_once()
    call_kwargs = page.screenshot.call_args[1]
    assert "login_redirect.png" in call_kwargs["path"]


# ---------------------------------------------------------------------------
# open() — no error screenshot when dir is None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_no_error_screenshot_when_dir_none():
    adapter = _make_adapter()  # error_screenshot_dir defaults to None
    page = _make_page(url="https://sso.example.com/login")
    adapter._context.new_page = AsyncMock(return_value=page)

    with pytest.raises(LoginRedirectError):
        await adapter.open("https://example.com/page")

    page.screenshot.assert_not_awaited()


# ---------------------------------------------------------------------------
# screenshot() — viewport mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_viewport(tmp_path):
    adapter = _make_adapter()
    page = _make_page()
    dest = tmp_path / "shot.png"

    await adapter.screenshot(page, dest, mode="viewport")
    page.screenshot.assert_awaited_once_with(path=str(dest))


# ---------------------------------------------------------------------------
# screenshot() — tiled mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_tiled(tmp_path):
    adapter = _make_adapter()
    page = _make_page(viewport_size={"width": 1280, "height": 720})
    # scroll_height=1440 → 2 tiles (1440/720)
    page.evaluate = AsyncMock(return_value=1440)
    dest = tmp_path / "shot.png"

    await adapter.screenshot(page, dest, mode="tiled")
    assert page.screenshot.await_count == 2


# ---------------------------------------------------------------------------
# screenshot() — tiled with viewport_size=None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_tiled_no_viewport(tmp_path):
    adapter = _make_adapter()
    page = _make_page()
    type(page).viewport_size = PropertyMock(return_value=None)
    page.evaluate = AsyncMock(return_value=1440)
    dest = tmp_path / "shot.png"

    with pytest.raises(RuntimeError, match="viewport size is not set"):
        await adapter.screenshot(page, dest, mode="tiled")


# ---------------------------------------------------------------------------
# screenshot() — invalid mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_invalid_mode(tmp_path):
    adapter = _make_adapter()
    page = _make_page()
    dest = tmp_path / "shot.png"

    with pytest.raises(ValueError, match="Unknown screenshot mode"):
        await adapter.screenshot(page, dest, mode="full_page")


# ---------------------------------------------------------------------------
# download_file()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_file(tmp_path):
    adapter = _make_adapter()
    page = _make_page()
    dest = tmp_path / "dl" / "report.csv"

    download_mock = AsyncMock()
    download_mock.save_as = AsyncMock()

    # Playwright's expect_download returns an async CM whose .value is awaitable
    future = asyncio.get_event_loop().create_future()
    future.set_result(download_mock)

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=False)
    cm.value = future
    page.expect_download = MagicMock(return_value=cm)

    result = await adapter.download_file(page, "#download-btn", dest)
    assert result == dest
    page.click.assert_awaited_once_with("#download-btn")
    download_mock.save_as.assert_awaited_once_with(str(dest))


# ---------------------------------------------------------------------------
# close() — idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_idempotent():
    adapter = _make_adapter()
    adapter._context.close = AsyncMock()
    adapter._browser.close = AsyncMock()
    adapter._playwright.stop = AsyncMock()

    await adapter.close()
    await adapter.close()  # second call should not raise


# ---------------------------------------------------------------------------
# _ensure_browser() — lazy launch (only once)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_browser_lazy():
    adapter = BrowserAdapter()
    launch_mock = AsyncMock()
    context_mock = AsyncMock()
    launch_mock.return_value = MagicMock()
    launch_mock.return_value.new_context = AsyncMock(return_value=context_mock)

    pw_mock = AsyncMock()
    pw_mock.chromium.launch = launch_mock

    with patch(
        "evidence_collector.adapters.browser.async_playwright"
    ) as mock_apw:
        mock_apw.return_value.start = AsyncMock(return_value=pw_mock)
        await adapter._ensure_browser()
        await adapter._ensure_browser()  # second call is no-op

    # launch called exactly once
    launch_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# _ensure_browser() — with profile_dir uses persistent context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_browser_persistent_context(tmp_path):
    adapter = BrowserAdapter(profile_dir=tmp_path / "profile")
    persistent_mock = AsyncMock()
    persistent_mock.return_value = MagicMock()
    persistent_mock.return_value.browser = MagicMock()

    pw_mock = AsyncMock()
    pw_mock.chromium.launch_persistent_context = persistent_mock

    with patch(
        "evidence_collector.adapters.browser.async_playwright"
    ) as mock_apw:
        mock_apw.return_value.start = AsyncMock(return_value=pw_mock)
        await adapter._ensure_browser()

    persistent_mock.assert_awaited_once()
    call_kwargs = persistent_mock.call_args[1]
    assert call_kwargs["user_data_dir"] == str(tmp_path / "profile")
