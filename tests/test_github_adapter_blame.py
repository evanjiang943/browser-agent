"""Tests for GitHubAdapter blame/search/diff methods with mock pages."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from evidence_collector.adapters.github import GitHubAdapter


@pytest.fixture
def mock_browser() -> AsyncMock:
    browser = AsyncMock()
    browser.open = AsyncMock()
    return browser


@pytest.fixture
def adapter(mock_browser: AsyncMock) -> GitHubAdapter:
    return GitHubAdapter(browser_adapter=mock_browser)


class TestOpenBlameView:
    def test_replaces_blob_with_blame(self, adapter, mock_browser):
        blame_page = AsyncMock()
        mock_browser.open = AsyncMock(return_value=blame_page)

        result = asyncio.run(
            adapter.open_blame_view(
                "https://github.com/org/repo/blob/main/src/hello.py"
            )
        )

        mock_browser.open.assert_called_once_with(
            "https://github.com/org/repo/blame/main/src/hello.py"
        )
        assert result is blame_page

    def test_no_blob_in_url(self, adapter, mock_browser):
        """If /blob/ is not present, URL is returned unchanged."""
        blame_page = AsyncMock()
        mock_browser.open = AsyncMock(return_value=blame_page)

        asyncio.run(
            adapter.open_blame_view("https://github.com/org/repo/main/file.py")
        )

        mock_browser.open.assert_called_once_with(
            "https://github.com/org/repo/main/file.py"
        )


class TestExtractBlameDates:
    def test_extracts_from_data_attributes(self, adapter):
        """Extracts blame dates from data-blame-line elements."""
        page = AsyncMock()

        async def query_selector(sel):
            if "data-blame-line='10'" in sel:
                el = AsyncMock()
                el.get_attribute = AsyncMock(
                    side_effect=lambda attr: {
                        "data-blame-date": "2025-03-01T12:00:00Z",
                        "data-blame-sha": "abc123",
                    }.get(attr, "")
                )
                return el
            if "data-blame-line='11'" in sel:
                el = AsyncMock()
                el.get_attribute = AsyncMock(
                    side_effect=lambda attr: {
                        "data-blame-date": "2025-02-15T10:00:00Z",
                        "data-blame-sha": "def456",
                    }.get(attr, "")
                )
                return el
            return None

        page.query_selector = AsyncMock(side_effect=query_selector)

        result = asyncio.run(adapter.extract_blame_dates(page, (10, 11)))

        assert len(result) == 2
        assert result[0] == {"line": 10, "date": "2025-03-01T12:00:00Z", "sha": "abc123"}
        assert result[1] == {"line": 11, "date": "2025-02-15T10:00:00Z", "sha": "def456"}

    def test_returns_empty_for_no_data(self, adapter):
        """Returns empty list when no blame data found."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)

        result = asyncio.run(adapter.extract_blame_dates(page, (1, 3)))
        assert result == []


class TestSearchCode:
    def test_returns_file_url_and_line_range(self, adapter, mock_browser):
        """Successful search returns file URL and line range."""
        search_page = AsyncMock()
        result_link = AsyncMock()
        result_link.get_attribute = AsyncMock(
            return_value="/org/repo/blob/main/src/hello.py#L10-L15"
        )
        search_page.query_selector = AsyncMock(return_value=result_link)
        search_page.close = AsyncMock()
        mock_browser.open = AsyncMock(return_value=search_page)

        result = asyncio.run(
            adapter.search_code("https://github.com/org/repo", "def hello()")
        )

        assert result is not None
        file_url, line_range = result
        assert file_url == "https://github.com/org/repo/blob/main/src/hello.py#L10-L15"
        assert line_range == (10, 15)

    def test_returns_none_when_no_results(self, adapter, mock_browser):
        """Returns None when search finds no results."""
        search_page = AsyncMock()
        search_page.query_selector = AsyncMock(return_value=None)
        search_page.close = AsyncMock()
        mock_browser.open = AsyncMock(return_value=search_page)

        result = asyncio.run(
            adapter.search_code("https://github.com/org/repo", "nonexistent_code_xyz")
        )

        assert result is None

    def test_single_line_range(self, adapter, mock_browser):
        """Single line URL fragment produces (N, N) range."""
        search_page = AsyncMock()
        result_link = AsyncMock()
        result_link.get_attribute = AsyncMock(
            return_value="/org/repo/blob/main/src/hello.py#L42"
        )
        search_page.query_selector = AsyncMock(return_value=result_link)
        search_page.close = AsyncMock()
        mock_browser.open = AsyncMock(return_value=search_page)

        result = asyncio.run(
            adapter.search_code("https://github.com/org/repo", "some code")
        )

        assert result is not None
        _, line_range = result
        assert line_range == (42, 42)

    def test_no_line_range_defaults(self, adapter, mock_browser):
        """URL without line fragment defaults to (1, 1)."""
        search_page = AsyncMock()
        result_link = AsyncMock()
        result_link.get_attribute = AsyncMock(
            return_value="/org/repo/blob/main/src/hello.py"
        )
        search_page.query_selector = AsyncMock(return_value=result_link)
        search_page.close = AsyncMock()
        mock_browser.open = AsyncMock(return_value=search_page)

        result = asyncio.run(
            adapter.search_code("https://github.com/org/repo", "some code")
        )

        assert result is not None
        _, line_range = result
        assert line_range == (1, 1)


class TestExtractCommitDiffSummary:
    def test_extracts_from_diffstat(self, adapter):
        """Extracts stats from structured diffstat element."""
        page = AsyncMock()

        stat_el = AsyncMock()
        stat_el.inner_text = AsyncMock(
            return_value="3 files changed, 25 additions, 10 deletions"
        )

        diff_el = AsyncMock()
        diff_el.inner_text = AsyncMock(return_value="+new line\n-old line")

        async def query_selector(sel):
            if "diffstat" in sel.lower():
                return stat_el
            if "diff" in sel.lower():
                return diff_el
            return None

        page.query_selector = AsyncMock(side_effect=query_selector)
        page.query_selector_all = AsyncMock(return_value=[])

        result = asyncio.run(adapter.extract_commit_diff_summary(page))

        assert result["files_changed"] == 3
        assert result["lines_added"] == 25
        assert result["lines_removed"] == 10

    def test_fallback_counting(self, adapter):
        """Falls back to counting +/- lines when no diffstat."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)

        diff_headers = [AsyncMock(), AsyncMock()]
        page.query_selector_all = AsyncMock(return_value=diff_headers)
        page.inner_text = AsyncMock(
            return_value="+ added line 1\n+ added line 2\n- removed line\n--- a/file.py\n+++ b/file.py"
        )

        result = asyncio.run(adapter.extract_commit_diff_summary(page))

        assert result["files_changed"] == 2
        assert result["lines_added"] == 2
        assert result["lines_removed"] == 1
