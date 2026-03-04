"""GitHub adapter — PR, commit, checks, and CI interactions."""

from __future__ import annotations

import re

from playwright.async_api import Page

from evidence_collector.utils.text import extract_jira_urls, extract_linear_urls


class GitHubAdapter:
    """GitHub-specific browser interactions for PRs, commits, checks, CI."""

    def __init__(self, browser_adapter) -> None:
        self.browser = browser_adapter

    async def open_pr(self, url: str) -> None:
        """Open a pull request page."""
        raise NotImplementedError

    async def open_commit(self, url: str) -> None:
        """Open a commit page."""
        raise NotImplementedError

    async def open_checks(self) -> None:
        """Navigate to the checks/status tab of the current PR."""
        raise NotImplementedError

    async def open_blame_view(self, file_url: str) -> None:
        """Switch a file view to blame mode."""
        raise NotImplementedError

    async def extract_blame_dates(self, line_range: tuple[int, int]) -> list[dict]:
        """Extract commit dates for specific lines from blame view."""
        raise NotImplementedError

    # ── Implemented extraction methods ──────────────────────────────

    async def extract_pr_metadata(self, page: Page) -> dict:
        """Extract PR metadata from the current page.

        Returns dict with: title, pr_or_commit_id, pr_creator, approvers,
        merger, merge_status.  Never raises on missing data — returns
        None / "unknown" / [] as appropriate.
        """
        # Title — strip trailing " #<number>" suffix
        title = None
        el = await page.query_selector(".pr-title")
        if el:
            raw = await el.inner_text()
            title = re.sub(r"\s*#\d+\s*$", "", raw).strip() or None

        # PR number
        pr_id = None
        el = await page.query_selector("[data-pr-number]")
        if el:
            pr_id = await el.get_attribute("data-pr-number")

        # Merge status
        merge_status = "unknown"
        el = await page.query_selector(".merge-status[data-status]")
        if el:
            raw_status = (await el.get_attribute("data-status") or "").lower()
            merge_status = raw_status if raw_status in ("merged", "open", "closed") else "unknown"

        # PR creator
        pr_creator = None
        el = await page.query_selector(".pr-author[data-user]")
        if not el:
            el = await page.query_selector(".pr-meta [data-user]")
        if el:
            pr_creator = await el.get_attribute("data-user")

        # Approvers
        approvers: list[str] = []
        els = await page.query_selector_all(
            "[data-section='reviewers'] [data-review='approved']"
        )
        for reviewer in els:
            user = await reviewer.get_attribute("data-user")
            if user:
                approvers.append(user)

        # Merger
        merger = None
        el = await page.query_selector("[data-section='merged-by'] [data-user]")
        if el:
            merger = await el.get_attribute("data-user")

        # Text fallback for creator/merger if selectors missed
        if not pr_creator or not merger:
            text = await page.inner_text("body")
            if not pr_creator:
                m = re.search(r"(\w+)\s+merged\s+\d+\s+commit", text)
                if m:
                    pr_creator = m.group(1)
            if not merger:
                m = re.search(r"Merged by\s+(\w+)", text, re.IGNORECASE)
                if m:
                    merger = m.group(1)

        return {
            "title": title,
            "pr_or_commit_id": pr_id,
            "pr_creator": pr_creator,
            "approvers": approvers,
            "merger": merger,
            "merge_status": merge_status,
        }

    async def extract_checks(self, page: Page) -> dict:
        """Extract CI check results from the current page.

        Returns dict with: check_summary, failed_checks,
        merged_with_failures, checks_raw.
        """
        checks_raw: list[dict] = []
        els = await page.query_selector_all("[data-check]")

        if els:
            for el in els:
                name = await el.get_attribute("data-check")
                status = await el.get_attribute("data-status") or "unknown"
                required = (await el.get_attribute("data-required") or "").lower() == "true"
                checks_raw.append({"name": name, "status": status, "required": required})
        else:
            # Text fallback: parse ✓/✗ markers
            text = await page.inner_text("[data-section='checks']") if await page.query_selector("[data-section='checks']") else ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if "✓" in line or "✗" in line:
                    status = "pass" if "✓" in line else "fail"
                    name = re.sub(r"[✓✗]", "", line).strip()
                    name = re.sub(r"\s*(Required|Optional).*", "", name).strip()
                    if name:
                        checks_raw.append({"name": name, "status": status, "required": True})

        # Summarize
        passed = sum(1 for c in checks_raw if c["status"] == "pass")
        failed = sum(1 for c in checks_raw if c["status"] == "fail")
        pending = sum(1 for c in checks_raw if c["status"] == "pending")
        optional = sum(1 for c in checks_raw if not c["required"])
        check_summary = f"passed={passed}; failed={failed}; pending={pending}; optional={optional}"

        failed_checks = [c["name"] for c in checks_raw if c["status"] == "fail"]

        # Determine merge status to check merged_with_failures
        merge_el = await page.query_selector(".merge-status[data-status]")
        merge_status = (await merge_el.get_attribute("data-status") or "").lower() if merge_el else ""
        merged_with_failures = merge_status == "merged" and len(failed_checks) > 0

        return {
            "check_summary": check_summary,
            "failed_checks": failed_checks,
            "merged_with_failures": merged_with_failures,
            "checks_raw": checks_raw,
        }

    async def find_ticket_links(self, page: Page) -> list[str]:
        """Find Jira, Linear, and GitHub issue links on the page.

        Returns a deduplicated list preserving first-seen order.
        """
        # Collect text from description section, falling back to full page
        desc_el = await page.query_selector("[data-section='description']")
        text = await desc_el.inner_text() if desc_el else await page.inner_text("body")

        # Collect all href values
        hrefs: list[str] = []
        for a in await page.query_selector_all("a[href]"):
            href = await a.get_attribute("href")
            if href:
                hrefs.append(href)
        href_text = " ".join(hrefs)

        combined = text + " " + href_text

        urls: list[str] = []
        urls.extend(extract_jira_urls(combined))
        urls.extend(extract_linear_urls(combined))

        # GitHub issue URLs from hrefs
        gh_pattern = re.compile(r"https://github\.com/[^/]+/[^/]+/issues/\d+")
        for href in hrefs:
            m = gh_pattern.match(href)
            if m:
                urls.append(m.group(0))

        # Deduplicate preserving order
        return list(dict.fromkeys(urls))

    async def get_ci_details_url(self, check_name: str, page: Page) -> str | None:
        """Get the CI details URL for a specific check.

        Returns the href of the details link, or None if not found.
        """
        el = await page.query_selector(f"[data-check='{check_name}']")
        if not el:
            return None

        link = await el.query_selector("a.check-details")
        if not link:
            # Fallback: any <a> containing "details" text
            for a in await el.query_selector_all("a"):
                text = (await a.inner_text()).lower()
                if "details" in text:
                    link = a
                    break

        if link:
            return await link.get_attribute("href")
        return None
