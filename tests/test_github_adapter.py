"""Tests for GitHubAdapter extraction methods against mock PR HTML."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

from evidence_collector.adapters.github import GitHubAdapter

MOCK_HTML = Path(__file__).resolve().parent.parent / "examples" / "mock_pr.html"
MOCK_CHECKS_HTML = Path(__file__).resolve().parent.parent / "examples" / "mock_pr_checks.html"


@pytest_asyncio.fixture
async def browser_and_pw():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    yield browser, pw
    await browser.close()
    await pw.stop()


@pytest_asyncio.fixture
async def page(browser_and_pw):
    browser, _pw = browser_and_pw
    p = await browser.new_page()
    await p.goto(f"file://{MOCK_HTML}")
    yield p
    await p.close()


@pytest_asyncio.fixture
async def checks_page(browser_and_pw):
    browser, _pw = browser_and_pw
    p = await browser.new_page()
    await p.goto(f"file://{MOCK_CHECKS_HTML}")
    yield p
    await p.close()


@pytest.fixture
def adapter():
    return GitHubAdapter(browser_adapter=None)


@pytest.mark.asyncio
async def test_extract_pr_metadata(adapter, page):
    result = await adapter.extract_pr_metadata(page)

    assert result["title"] == "Add rate limiting to payment processor"
    # PR number falls back to .f1-light since file:// URL has no /pull/42
    assert result["pr_or_commit_id"] == "42"
    assert result["pr_creator"] == "alice"
    assert result["approvers"] == ["bob", "carol"]
    assert result["merger"] == "dave"
    assert result["merge_status"] == "merged"


@pytest.mark.asyncio
async def test_extract_checks(adapter, checks_page):
    result = await adapter.extract_checks(checks_page)

    assert result["check_summary"] == "passed=3; failed=1; pending=0; optional=1"
    assert result["failed_checks"] == ["security-scan"]
    assert result["merged_with_failures"] is True
    assert len(result["checks_raw"]) == 4


@pytest.mark.asyncio
async def test_find_ticket_links(adapter, page):
    result = await adapter.find_ticket_links(page)

    assert len(result) == 2
    assert "https://acme-corp.atlassian.net/browse/ENG-123" in result
    assert "https://acme-corp.atlassian.net/browse/ENG-456" in result


@pytest.mark.asyncio
async def test_get_ci_details_url(adapter, checks_page):
    url = await adapter.get_ci_details_url("ci/tests", checks_page)
    assert url == "https://ci.example.com/tests/123"

    url = await adapter.get_ci_details_url("nonexistent-check", checks_page)
    assert url is None
