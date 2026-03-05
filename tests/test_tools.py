"""Tests for agent tool functions."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from evidence_collector.agent.loop import AgentContext
from evidence_collector.agent.task import OutputField, TaskDescription
from evidence_collector.agent.tools import (
    build_tool_schemas,
    click_element,
    close_page,
    evaluate_js,
    execute_tool,
    get_page_url,
    get_recorded_fields,
    get_required_fields,
    open_url,
    query_selector_all_text,
    query_selector_text,
    read_page_text,
    record_field,
    save_download,
    scroll_page,
    take_screenshot,
    tool_find_links,
)
from evidence_collector.config import AgentConfig
from evidence_collector.evidence.manifest import SampleNotes


@pytest.fixture
def task():
    return TaskDescription(
        task_name="test",
        goal="Test",
        instructions="Test",
        input_columns=["url"],
        output_schema=[
            OutputField(name="title", description="Title"),
            OutputField(name="status", description="Status"),
            OutputField(name="notes", description="Notes", required=False),
        ],
    )


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.query_selector.return_value = None
    page.query_selector_all.return_value = []
    page.close = AsyncMock()
    page.inner_text = AsyncMock(return_value="Page body text")
    page.evaluate = AsyncMock(return_value=0)
    page.wait_for_timeout = AsyncMock()
    page.url = "https://example.com/page"
    page.viewport_size = {"width": 1280, "height": 720}
    return page


@pytest.fixture
def mock_browser(mock_page):
    browser = AsyncMock()
    browser.open = AsyncMock(return_value=mock_page)
    browser.screenshot = AsyncMock()
    browser.download_file = AsyncMock()
    browser.close = AsyncMock()
    browser.timeout = 30000
    return browser


@pytest.fixture
def ctx(task, mock_browser, tmp_path):
    sample_dir = tmp_path / "sample-1"
    sample_dir.mkdir()
    (sample_dir / "screenshots").mkdir()
    (sample_dir / "downloads").mkdir()

    run_logger = MagicMock()
    run_logger.log = MagicMock()

    return AgentContext(
        sample_id="sample-1",
        input={"url": "https://example.com"},
        task=task,
        sample_dir=sample_dir,
        browser=mock_browser,
        run_logger=run_logger,
        config=AgentConfig(),
    )


class TestOpenUrl:
    def test_success(self, ctx, mock_page):
        mock_page.title = AsyncMock(return_value="Example Page")
        result = asyncio.run(open_url(ctx, "https://example.com"))
        assert result["page_id"] == "page_0"
        assert result["title"] == "Example Page"
        assert "page_0" in ctx.pages

    def test_max_pages(self, ctx):
        ctx.task.max_pages_per_sample = 0
        result = asyncio.run(open_url(ctx, "https://example.com"))
        assert result["error"] == "MAX_PAGES_REACHED"

    def test_auth_error(self, ctx, mock_browser):
        from evidence_collector.adapters.browser import LoginRedirectError
        mock_browser.open.side_effect = LoginRedirectError("Login required")
        result = asyncio.run(open_url(ctx, "https://example.com"))
        assert result["error"] == "AUTH_REQUIRED"

    def test_not_found(self, ctx, mock_browser):
        from evidence_collector.adapters.browser import PageNotFoundError
        mock_browser.open.side_effect = PageNotFoundError("404")
        result = asyncio.run(open_url(ctx, "https://example.com"))
        assert result["error"] == "PAGE_NOT_FOUND"


class TestClickElement:
    def test_success(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        result = asyncio.run(click_element(ctx, "page_0", "button.submit"))
        assert result["success"] is True

    def test_invalid_page(self, ctx):
        result = asyncio.run(click_element(ctx, "nonexistent", "button"))
        assert result["error"] == "INVALID_PAGE_ID"

    def test_click_failure(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        mock_page.click.side_effect = Exception("Element not found")
        result = asyncio.run(click_element(ctx, "page_0", "button"))
        assert result["error"] == "CLICK_FAILED"


class TestScrollPage:
    def test_scroll_down(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        mock_page.evaluate = AsyncMock(return_value=500)
        result = asyncio.run(scroll_page(ctx, "page_0", "down"))
        assert "scroll_y" in result

    def test_invalid_page(self, ctx):
        result = asyncio.run(scroll_page(ctx, "nonexistent", "down"))
        assert result["error"] == "INVALID_PAGE_ID"


class TestClosePage:
    def test_success(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        result = asyncio.run(close_page(ctx, "page_0"))
        assert result["success"] is True
        assert "page_0" not in ctx.pages

    def test_invalid_page(self, ctx):
        result = asyncio.run(close_page(ctx, "nonexistent"))
        assert result["error"] == "INVALID_PAGE_ID"


class TestReadPageText:
    def test_success(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        result = asyncio.run(read_page_text(ctx, "page_0"))
        assert result["text"] == "Page body text"
        assert result["truncated"] is False

    def test_truncation(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        result = asyncio.run(read_page_text(ctx, "page_0", max_chars=5))
        assert result["text"] == "Page "
        assert result["truncated"] is True


class TestQuerySelectorText:
    def test_found(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value="Title Text")
        el.get_attribute = AsyncMock(return_value=None)
        el.evaluate = AsyncMock(return_value="h1")
        mock_page.query_selector.return_value = el
        result = asyncio.run(query_selector_text(ctx, "page_0", "h1"))
        assert result["found"] is True
        assert result["text"] == "Title Text"
        assert result["tag"] == "h1"

    def test_not_found(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        mock_page.query_selector.return_value = None
        result = asyncio.run(query_selector_text(ctx, "page_0", ".missing"))
        assert result["found"] is False


class TestQuerySelectorAllText:
    def test_multiple(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        el1 = AsyncMock()
        el1.inner_text = AsyncMock(return_value="Item 1")
        el1.get_attribute = AsyncMock(return_value="/link1")
        el1.evaluate = AsyncMock(return_value="a")
        el2 = AsyncMock()
        el2.inner_text = AsyncMock(return_value="Item 2")
        el2.get_attribute = AsyncMock(return_value=None)
        el2.evaluate = AsyncMock(return_value="span")
        mock_page.query_selector_all.return_value = [el1, el2]
        result = asyncio.run(query_selector_all_text(ctx, "page_0", "li"))
        assert result["count"] == 2
        assert len(result["items"]) == 2
        assert result["items"][0]["text"] == "Item 1"


class TestRecordField:
    def test_valid_field(self, ctx):
        result = asyncio.run(record_field(ctx, "title", "My Title"))
        assert result["success"] is True
        assert ctx.recorded_fields["title"] == "My Title"

    def test_invalid_field(self, ctx):
        result = asyncio.run(record_field(ctx, "unknown_field", "value"))
        assert result["error"] == "INVALID_FIELD"
        assert "unknown_field" not in ctx.recorded_fields


class TestGetRequiredFields:
    def test_all_missing(self, ctx):
        result = asyncio.run(get_required_fields(ctx))
        assert "title" in result["missing"]
        assert "status" in result["missing"]
        assert result["filled"] == []

    def test_partial(self, ctx):
        ctx.recorded_fields["title"] = "Test"
        result = asyncio.run(get_required_fields(ctx))
        assert "title" in result["filled"]
        assert "status" in result["missing"]


class TestGetRecordedFields:
    def test_returns_fields(self, ctx):
        ctx.recorded_fields["title"] = "Test"
        result = asyncio.run(get_recorded_fields(ctx))
        assert result["fields"]["title"] == "Test"


class TestTakeScreenshot:
    def test_success(self, ctx, mock_page):
        ctx.pages["page_0"] = mock_page
        result = asyncio.run(take_screenshot(ctx, "page_0", "overview"))
        assert "filename" in result
        assert len(ctx.notes.screenshots) == 1

    def test_invalid_page(self, ctx):
        result = asyncio.run(take_screenshot(ctx, "nonexistent", "test"))
        assert result["error"] == "INVALID_PAGE_ID"


class TestExecuteTool:
    def test_dispatch_record_field(self, ctx):
        result = asyncio.run(execute_tool(ctx, "record_field", {
            "field_name": "title", "value": "Test"
        }))
        assert result["success"] is True

    def test_unknown_tool(self, ctx):
        result = asyncio.run(execute_tool(ctx, "nonexistent_tool", {}))
        assert result["error"] == "UNKNOWN_TOOL"

    def test_dispatch_get_required_fields(self, ctx):
        result = asyncio.run(execute_tool(ctx, "get_required_fields", {}))
        assert "missing" in result

    def test_dispatch_get_recorded_fields(self, ctx):
        result = asyncio.run(execute_tool(ctx, "get_recorded_fields", {}))
        assert "fields" in result


class TestBuildToolSchemas:
    def test_returns_15_tools(self):
        schemas = build_tool_schemas()
        assert len(schemas) == 15

    def test_schema_format(self):
        schemas = build_tool_schemas()
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            assert schema["input_schema"]["type"] == "object"

    def test_tool_names(self):
        schemas = build_tool_schemas()
        names = {s["name"] for s in schemas}
        expected = {
            "open_url", "click_element", "scroll_page", "close_page",
            "read_page_text", "query_selector_text", "query_selector_all_text",
            "find_links", "get_page_url", "evaluate_js",
            "take_screenshot", "save_download", "record_field",
            "get_required_fields", "get_recorded_fields",
        }
        assert names == expected
