"""Shared pytest fixtures for browser/page mocks."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_page() -> AsyncMock:
    page = AsyncMock()
    page.query_selector.return_value = None
    page.query_selector_all.return_value = []
    page.close = AsyncMock()
    page.inner_text = AsyncMock(return_value="")
    page.evaluate = AsyncMock(return_value=0)
    page.wait_for_timeout = AsyncMock()
    return page


@pytest.fixture
def mock_browser(mock_page: AsyncMock) -> AsyncMock:
    browser = AsyncMock()
    browser.open = AsyncMock(return_value=mock_page)
    browser.screenshot = AsyncMock()
    browser.close = AsyncMock()
    return browser
