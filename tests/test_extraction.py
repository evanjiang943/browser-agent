"""Tests for generic extraction layer (extract_fields, find_links_matching, verify_url).

All tests use mocked Playwright Page objects — no real browser is launched.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from evidence_collector.adapters.browser import (
    ExtractionRule,
    extract_fields,
    find_links_matching,
    verify_url,
)


# ── Mock page builder ───────────────────────────────────────────────────


def _make_mock_page(
    elements: dict[str, str] | None = None,
    links: list[dict[str, str]] | None = None,
    body_text: str = "",
) -> AsyncMock:
    """Build a mock Playwright Page from a declarative spec.

    *elements*: ``{css_selector: text_content}`` — only exact selector
    matches work (like a real page.query_selector).

    *links*: list of ``{"href": url}`` dicts representing ``<a>`` elements.

    *body_text*: the full visible text returned by ``page.inner_text("body")``.
    """
    elements = elements or {}
    links = links or []

    async def query_selector(selector: str):
        if selector in elements:
            el = AsyncMock()
            el.inner_text = AsyncMock(return_value=elements[selector])
            return el
        return None

    async def query_selector_all(selector: str):
        if selector == "a[href]":
            result = []
            for link in links:
                el = AsyncMock()
                el.get_attribute = AsyncMock(return_value=link.get("href"))
                result.append(el)
            return result
        return []

    async def inner_text(selector: str):
        if selector == "body":
            return body_text
        return ""

    page = AsyncMock()
    page.query_selector = AsyncMock(side_effect=query_selector)
    page.query_selector_all = AsyncMock(side_effect=query_selector_all)
    page.inner_text = AsyncMock(side_effect=inner_text)
    return page


# ── extract_fields ───────────────────────────────────────────────────────


class TestExtractFields:
    def test_selector_match(self):
        page = _make_mock_page(elements={
            "h1.title": "Fix auth bug",
            ".assignee": "alice",
        })
        rules = [
            ExtractionRule(field="title", selectors=["h1.title"]),
            ExtractionRule(field="assignee", selectors=[".assignee"]),
        ]
        result = asyncio.run(extract_fields(page, rules))
        assert result == {"title": "Fix auth bug", "assignee": "alice"}

    def test_selector_priority(self):
        """First matching selector wins."""
        page = _make_mock_page(elements={
            "[data-testid='title']": "Primary",
            "h1": "Fallback",
        })
        rules = [
            ExtractionRule(
                field="title",
                selectors=["[data-testid='title']", "h1"],
            ),
        ]
        result = asyncio.run(extract_fields(page, rules))
        assert result["title"] == "Primary"

    def test_selector_falls_through_empty(self):
        """If first selector returns empty text, try next."""
        page = _make_mock_page(elements={
            ".primary": "",
            ".secondary": "Actual value",
        })
        rules = [
            ExtractionRule(
                field="title",
                selectors=[".primary", ".secondary"],
            ),
        ]
        result = asyncio.run(extract_fields(page, rules))
        assert result["title"] == "Actual value"

    def test_fallback_pattern(self):
        page = _make_mock_page(
            body_text="Assigned to: bob\nDue: 2026-04-01"
        )
        rules = [
            ExtractionRule(
                field="assignee",
                selectors=[".no-match"],
                fallback_pattern=r"Assigned to:\s*(\S+)",
            ),
        ]
        result = asyncio.run(extract_fields(page, rules))
        assert result["assignee"] == "bob"

    def test_fallback_pattern_no_group(self):
        """Regex without capture group returns full match."""
        page = _make_mock_page(body_text="Status: OPEN")
        rules = [
            ExtractionRule(
                field="status",
                selectors=[],
                fallback_pattern=r"OPEN|CLOSED",
            ),
        ]
        result = asyncio.run(extract_fields(page, rules))
        assert result["status"] == "OPEN"

    def test_transform(self):
        page = _make_mock_page(elements={".tag": "  IN PROGRESS  "})
        rules = [
            ExtractionRule(
                field="status",
                selectors=[".tag"],
                transform=str.lower,
            ),
        ]
        result = asyncio.run(extract_fields(page, rules))
        assert result["status"] == "in progress"

    def test_missing_field_returns_empty(self):
        page = _make_mock_page()
        rules = [
            ExtractionRule(field="ghost", selectors=[".nope"]),
        ]
        result = asyncio.run(extract_fields(page, rules))
        assert result["ghost"] == ""

    def test_required_field_logs_warning(self, caplog):
        page = _make_mock_page()
        rules = [
            ExtractionRule(
                field="critical",
                selectors=[".nope"],
                required=True,
            ),
        ]
        import logging

        with caplog.at_level(logging.WARNING):
            result = asyncio.run(extract_fields(page, rules))

        assert result["critical"] == ""
        assert any("critical" in r.message for r in caplog.records)

    def test_no_rules_returns_empty_dict(self):
        page = _make_mock_page()
        result = asyncio.run(extract_fields(page, []))
        assert result == {}

    def test_multiple_rules_mixed(self):
        page = _make_mock_page(
            elements={"h1": "Bug Report", ".status": "Open"},
            body_text="Priority: HIGH\nAssigned to: carol",
        )
        rules = [
            ExtractionRule(field="title", selectors=["h1"]),
            ExtractionRule(field="status", selectors=[".status"]),
            ExtractionRule(
                field="priority",
                selectors=[".priority"],
                fallback_pattern=r"Priority:\s*(\w+)",
            ),
            ExtractionRule(field="missing", selectors=[".nah"]),
        ]
        result = asyncio.run(extract_fields(page, rules))
        assert result == {
            "title": "Bug Report",
            "status": "Open",
            "priority": "HIGH",
            "missing": "",
        }

    def test_body_text_fetched_once(self):
        """inner_text('body') should only be called once even with multiple fallbacks."""
        page = _make_mock_page(body_text="abc 123")
        rules = [
            ExtractionRule(
                field="a", selectors=[], fallback_pattern=r"(abc)"
            ),
            ExtractionRule(
                field="b", selectors=[], fallback_pattern=r"(\d+)"
            ),
        ]
        asyncio.run(extract_fields(page, rules))
        # inner_text called exactly once for "body"
        body_calls = [
            c for c in page.inner_text.call_args_list if c.args == ("body",)
        ]
        assert len(body_calls) == 1


# ── find_links_matching ──────────────────────────────────────────────────


class TestFindLinksMatching:
    def test_matches_single_pattern(self):
        page = _make_mock_page(links=[
            {"href": "https://jira.example.com/browse/PROJ-1"},
            {"href": "https://example.com/unrelated"},
            {"href": "https://jira.example.com/browse/PROJ-2"},
        ])
        result = asyncio.run(
            find_links_matching(page, [r"jira\.example\.com/browse/"])
        )
        assert result == [
            "https://jira.example.com/browse/PROJ-1",
            "https://jira.example.com/browse/PROJ-2",
        ]

    def test_matches_multiple_patterns(self):
        page = _make_mock_page(links=[
            {"href": "https://jira.example.com/browse/X-1"},
            {"href": "https://github.com/org/repo/issues/42"},
            {"href": "https://example.com/docs"},
        ])
        result = asyncio.run(
            find_links_matching(page, [
                r"jira\.example\.com/browse/",
                r"github\.com/.+/issues/\d+",
            ])
        )
        assert result == [
            "https://jira.example.com/browse/X-1",
            "https://github.com/org/repo/issues/42",
        ]

    def test_deduplicates(self):
        page = _make_mock_page(links=[
            {"href": "https://jira.example.com/browse/A-1"},
            {"href": "https://jira.example.com/browse/A-1"},
        ])
        result = asyncio.run(
            find_links_matching(page, [r"jira\.example\.com"])
        )
        assert result == ["https://jira.example.com/browse/A-1"]

    def test_preserves_order(self):
        page = _make_mock_page(links=[
            {"href": "https://b.com/2"},
            {"href": "https://a.com/1"},
            {"href": "https://c.com/3"},
        ])
        result = asyncio.run(find_links_matching(page, [r".*"]))
        assert result == [
            "https://b.com/2",
            "https://a.com/1",
            "https://c.com/3",
        ]

    def test_no_matches(self):
        page = _make_mock_page(links=[
            {"href": "https://example.com/page"},
        ])
        result = asyncio.run(
            find_links_matching(page, [r"jira\.example\.com"])
        )
        assert result == []

    def test_empty_links(self):
        page = _make_mock_page(links=[])
        result = asyncio.run(find_links_matching(page, [r".*"]))
        assert result == []

    def test_skips_none_href(self):
        page = _make_mock_page(links=[
            {"href": None},
            {"href": "https://jira.example.com/browse/X-1"},
        ])
        result = asyncio.run(
            find_links_matching(page, [r"jira\.example\.com"])
        )
        assert result == ["https://jira.example.com/browse/X-1"]


# ── verify_url ───────────────────────────────────────────────────────────


class TestVerifyUrl:
    def _mock_session(self, status=200, url="https://example.com", method_not_allowed=False):
        """Build a mock aiohttp.ClientSession."""
        session = AsyncMock()

        resp = AsyncMock()
        resp.status = 405 if method_not_allowed else status
        resp.url = MagicMock()
        resp.url.__str__ = lambda self: url
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        if method_not_allowed:
            get_resp = AsyncMock()
            get_resp.status = status
            get_resp.url = MagicMock()
            get_resp.url.__str__ = lambda self: url
            get_resp.__aenter__ = AsyncMock(return_value=get_resp)
            get_resp.__aexit__ = AsyncMock(return_value=False)
            session.get = MagicMock(return_value=get_resp)

        session.head = MagicMock(return_value=resp)
        return session

    def test_alive(self):
        session = self._mock_session(status=200, url="https://example.com")
        result = asyncio.run(verify_url("https://example.com", session))
        assert result["alive"] is True
        assert result["status_code"] == 200
        assert result["redirect_url"] is None
        assert result["error"] is None

    def test_redirect(self):
        session = self._mock_session(
            status=200, url="https://example.com/final"
        )
        result = asyncio.run(verify_url("https://example.com", session))
        assert result["alive"] is True
        assert result["redirect_url"] == "https://example.com/final"

    def test_404(self):
        session = self._mock_session(status=404, url="https://example.com")
        result = asyncio.run(verify_url("https://example.com", session))
        assert result["alive"] is False
        assert result["status_code"] == 404

    def test_server_error(self):
        session = self._mock_session(status=500, url="https://example.com")
        result = asyncio.run(verify_url("https://example.com", session))
        assert result["alive"] is False
        assert result["status_code"] == 500

    def test_connection_error(self):
        session = AsyncMock()
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
        resp.__aexit__ = AsyncMock(return_value=False)
        session.head = MagicMock(return_value=resp)

        result = asyncio.run(verify_url("https://down.example.com", session))
        assert result["alive"] is False
        assert result["status_code"] is None
        assert "refused" in result["error"]

    def test_head_405_falls_back_to_get(self):
        session = self._mock_session(
            status=200, url="https://example.com", method_not_allowed=True
        )
        result = asyncio.run(verify_url("https://example.com", session))
        assert result["alive"] is True
        assert result["status_code"] == 200
        session.get.assert_called_once()
