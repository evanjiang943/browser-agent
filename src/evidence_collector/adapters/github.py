"""GitHub adapter — PR, commit, checks, and CI interactions."""

from __future__ import annotations

import re
from urllib.parse import quote, urlparse

from playwright.async_api import Page

from evidence_collector.utils.text import extract_jira_urls, extract_linear_urls


class GitHubAdapter:
    """GitHub-specific browser interactions for PRs, commits, checks, CI."""

    def __init__(self, browser_adapter) -> None:
        self.browser = browser_adapter

    async def open_pr(self, url: str) -> Page:
        """Open a pull request page."""
        return await self.browser.open(url)

    async def open_commit(self, url: str) -> Page:
        """Open a commit page."""
        return await self.browser.open(url)

    async def open_checks(self) -> None:
        """Navigate to the checks/status tab of the current PR."""
        raise NotImplementedError

    async def open_blame_view(self, file_url: str) -> Page:
        """Switch a file view to blame mode by replacing /blob/ with /blame/."""
        blame_url = file_url.replace("/blob/", "/blame/", 1)
        return await self.browser.open(blame_url)

    async def extract_blame_dates(
        self, page: Page, line_range: tuple[int, int]
    ) -> list[dict]:
        """Extract commit dates and SHAs from blame annotations for a line range.

        Returns list of dicts with keys: line, date, sha.
        """
        start, end = line_range
        results: list[dict] = []

        for line_num in range(start, end + 1):
            # Try data-attribute selectors first (structured blame view)
            row = await page.query_selector(
                f"[data-blame-line='{line_num}']"
            )
            if row:
                date = await row.get_attribute("data-blame-date") or ""
                sha = await row.get_attribute("data-blame-sha") or ""
                if date or sha:
                    results.append({"line": line_num, "date": date, "sha": sha})
                    continue

            # Fallback: look for blame-commit-date and blame-commit-sha in line containers
            row = await page.query_selector(f"#LC{line_num}")
            if not row:
                row = await page.query_selector(f"[data-line-number='{line_num}']")
            if row:
                parent = await row.evaluate_handle("el => el.closest('.blame-hunk, .blame-line, tr')")
                if parent:
                    date_el = await parent.as_element().query_selector(
                        "[data-blame-date], time, .blame-commit-date"
                    )
                    sha_el = await parent.as_element().query_selector(
                        "[data-blame-sha], a.blame-commit-link, .blame-sha"
                    )
                    date = ""
                    sha = ""
                    if date_el:
                        date = (
                            await date_el.get_attribute("datetime")
                            or await date_el.get_attribute("data-blame-date")
                            or (await date_el.inner_text()).strip()
                        )
                    if sha_el:
                        sha = (
                            await sha_el.get_attribute("data-blame-sha")
                            or await sha_el.get_attribute("href")
                            or (await sha_el.inner_text()).strip()
                        )
                        # Extract bare SHA from href like /org/repo/commit/abc123
                        if "/" in sha:
                            sha = sha.rstrip("/").rsplit("/", 1)[-1]
                    if date or sha:
                        results.append({"line": line_num, "date": date, "sha": sha})

        return results

    async def search_code(
        self, repo_url: str, query: str
    ) -> tuple[str, tuple[int, int]] | None:
        """Search for code in a GitHub repo and return the first result.

        Returns (file_url, (start_line, end_line)) or None if no results.
        """
        # Extract owner/repo from URL
        parsed = urlparse(repo_url.rstrip("/"))
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 2:
            return None
        owner_repo = f"{path_parts[0]}/{path_parts[1]}"

        search_url = (
            f"https://github.com/search?q={quote(query)}"
            f"+repo:{quote(owner_repo)}&type=code"
        )
        page = await self.browser.open(search_url)

        try:
            # Look for the first code result link
            result_link = await page.query_selector(
                "[data-testid='result'] a, .code-list-item a, .search-result a"
            )
            if not result_link:
                return None

            file_url = await result_link.get_attribute("href") or ""
            if not file_url:
                return None

            # Make absolute if relative
            if file_url.startswith("/"):
                file_url = f"https://github.com{file_url}"

            # Extract line range from URL fragment (#L10-L20 or #L10)
            line_range = (1, 1)
            m = re.search(r"#L(\d+)(?:-L(\d+))?", file_url)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else start
                line_range = (start, end)

            return file_url, line_range
        finally:
            await page.close()

    async def extract_commit_diff_summary(self, page: Page) -> dict:
        """Extract diff summary from a commit page.

        Returns dict with: files_changed, lines_added, lines_removed, diff_text_snippet.
        """
        files_changed = 0
        lines_added = 0
        lines_removed = 0
        diff_text_snippet = ""

        # Try structured diff stats
        stat_el = await page.query_selector(
            "[data-section='diffstat'], .diffstat, #diffstat"
        )
        if stat_el:
            stat_text = await stat_el.inner_text()
            m = re.search(r"(\d+)\s+files?\s+changed", stat_text)
            if m:
                files_changed = int(m.group(1))
            m = re.search(r"(\d+)\s+additions?", stat_text)
            if m:
                lines_added = int(m.group(1))
            m = re.search(r"(\d+)\s+deletions?", stat_text)
            if m:
                lines_removed = int(m.group(1))
        else:
            # Fallback: count file diff headers
            diff_files = await page.query_selector_all(
                ".file-header, [data-file-type], .diff-file-header"
            )
            files_changed = len(diff_files)

            # Count +/- lines
            body_text = await page.inner_text("body")
            for line in body_text.splitlines():
                stripped = line.strip()
                if stripped.startswith("+") and not stripped.startswith("+++"):
                    lines_added += 1
                elif stripped.startswith("-") and not stripped.startswith("---"):
                    lines_removed += 1

        # Extract a snippet of the diff for materiality assessment
        diff_el = await page.query_selector(
            ".diff-table, .blob-code-inner, [data-section='diff']"
        )
        if diff_el:
            raw = await diff_el.inner_text()
            diff_text_snippet = raw[:500]

        return {
            "files_changed": files_changed,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "diff_text_snippet": diff_text_snippet,
        }

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
