"""GitHub adapter — PR, commit, checks, and CI interactions."""

from __future__ import annotations


class GitHubAdapter:
    """GitHub-specific browser interactions for PRs, commits, checks, CI."""

    def __init__(self, browser_adapter) -> None:
        self.browser = browser_adapter

    async def open_pr(self, url: str) -> None:
        """Open a pull request page."""
        # TODO: navigate to PR URL, wait for PR header to load
        raise NotImplementedError

    async def extract_pr_metadata(self) -> dict:
        """Extract PR creator, approvers, merger from current page."""
        # TODO: extract PR metadata using selectors or text heuristics
        raise NotImplementedError

    async def open_checks(self) -> None:
        """Navigate to the checks/status tab of the current PR."""
        # TODO: click checks tab, wait for checks list to load
        raise NotImplementedError

    async def extract_check_results(self) -> list[dict]:
        """Extract check names, statuses (pass/fail/optional)."""
        # TODO: parse checks list into structured results
        raise NotImplementedError

    async def detect_jira_link(self) -> str | None:
        """Find a Jira/Linear link in the PR description or commits."""
        # TODO: scan page content for Jira/Linear URL patterns
        raise NotImplementedError

    async def open_commit(self, url: str) -> None:
        """Open a commit page."""
        # TODO: navigate to commit URL, wait for diff to load
        raise NotImplementedError

    async def open_blame_view(self, file_url: str) -> None:
        """Switch a file view to blame mode."""
        # TODO: navigate to blame view URL
        raise NotImplementedError

    async def extract_blame_dates(self, line_range: tuple[int, int]) -> list[dict]:
        """Extract commit dates for specific lines from blame view."""
        # TODO: parse blame annotations for given line range
        raise NotImplementedError
