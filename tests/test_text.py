"""Tests for utils/text.py."""

from evidence_collector.utils.text import (
    extract_jira_urls,
    extract_linear_urls,
    extract_ticket_id,
    normalize_whitespace,
)


class TestNormalizeWhitespace:
    def test_basic(self):
        assert normalize_whitespace("  hello   world  ") == "hello world"

    def test_tabs_and_newlines(self):
        assert normalize_whitespace("a\t\nb\n\nc") == "a b c"

    def test_empty(self):
        assert normalize_whitespace("") == ""

    def test_single_word(self):
        assert normalize_whitespace("  hello  ") == "hello"


class TestExtractJiraUrls:
    def test_single_match(self):
        text = "See https://mycompany.atlassian.net/browse/PROJ-123 for details"
        assert extract_jira_urls(text) == [
            "https://mycompany.atlassian.net/browse/PROJ-123"
        ]

    def test_multiple(self):
        text = (
            "https://jira.example.com/browse/ABC-1 and "
            "https://jira.example.com/browse/DEF-99"
        )
        result = extract_jira_urls(text)
        assert len(result) == 2

    def test_none_found(self):
        assert extract_jira_urls("no urls here") == []

    def test_non_browse_url_ignored(self):
        assert extract_jira_urls("https://jira.example.com/issues/PROJ-1") == []


class TestExtractLinearUrls:
    def test_single_match(self):
        text = "Check https://linear.app/my-team/issue/ENG-42 please"
        assert extract_linear_urls(text) == [
            "https://linear.app/my-team/issue/ENG-42"
        ]

    def test_none_found(self):
        assert extract_linear_urls("nothing here") == []


class TestExtractTicketId:
    def test_jira_url(self):
        assert (
            extract_ticket_id("https://jira.example.com/browse/PROJ-123") == "PROJ-123"
        )

    def test_linear_url(self):
        assert (
            extract_ticket_id("https://linear.app/team/issue/ENG-42") == "ENG-42"
        )

    def test_generic_url(self):
        assert extract_ticket_id("https://example.com/tickets/ABC-7") == "ABC-7"

    def test_no_ticket_pattern_fallback(self):
        assert extract_ticket_id("https://example.com/users/johndoe") == "johndoe"

    def test_empty_path(self):
        assert extract_ticket_id("https://example.com") is None

    def test_trailing_slash(self):
        assert extract_ticket_id("https://example.com/page/") == "page"
