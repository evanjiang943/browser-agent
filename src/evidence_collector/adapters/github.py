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

    async def open_checks(self, page: Page) -> Page:
        """Navigate to the checks tab of the current PR.

        Clicks the Checks tab link or constructs the URL from the current page URL.
        Returns the page after navigation.
        """
        # Try clicking the Checks tab link
        checks_link = await page.query_selector(
            'a.tabnav-tab[href*="/checks"], '
            'a[data-tab-item="checks"], '
            'a[href$="/checks"]'
        )
        if checks_link:
            href = await checks_link.get_attribute("href")
            if href:
                # Navigate directly — more reliable than click for SPAs
                if href.startswith("/"):
                    href = f"https://github.com{href}"
                return await self.browser.open(href)
            await checks_link.click()
            await page.wait_for_load_state("networkidle")
            return page

        # Fallback: construct checks URL from current URL
        current = page.url
        m = re.match(r"(https://github\.com/[^/]+/[^/]+/pull/\d+)", current)
        if m:
            checks_url = m.group(1).rstrip("/") + "/checks"
            return await self.browser.open(checks_url)

        return page

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
        # ── Title ───────────────────────────────────────────────────
        title = None

        # Primary: bdi.js-issue-title (works in mock HTML and some GitHub views)
        el = await page.query_selector("bdi.js-issue-title")
        if el:
            title = (await el.inner_text()).strip() or None

        # Fallback: h1.gh-header-title (skip bare h1 — real GitHub has
        # a sr-only search h1 as first on page)
        if not title:
            el = await page.query_selector("h1.gh-header-title")
            if el:
                raw = await el.inner_text()
                title = re.sub(r"\s*#\d+\s*$", "", raw).strip() or None

        # Fallback: page <title> — format: "Title by author · Pull Request #N · org/repo"
        if not title:
            page_title = await page.title()
            m = re.match(r"^(.+?)\s*(?:by\s+\S+\s*)?·\s*Pull Request", page_title)
            if m:
                title = m.group(1).strip()

        # ── PR number — extract from URL (authoritative) ───────────
        pr_id = None
        m = re.search(r"/pull/(\d+)", page.url)
        if m:
            pr_id = m.group(1)

        # Fallback: .f1-light span with #N text
        if not pr_id:
            el = await page.query_selector(".gh-header-title .f1-light")
            if el:
                text = (await el.inner_text()).strip()
                m = re.match(r"#(\d+)", text)
                if m:
                    pr_id = m.group(1)

        # ── Merge status ────────────────────────────────────────────
        merge_status = "unknown"

        # Primary: .State element class/text (works on real GitHub)
        el = await page.query_selector(".State")
        if el:
            classes = await el.get_attribute("class") or ""
            text = (await el.inner_text()).strip().lower()
            if "State--merged" in classes or text == "merged":
                merge_status = "merged"
            elif "State--open" in classes or text == "open":
                merge_status = "open"
            elif "State--closed" in classes or text == "closed":
                merge_status = "closed"

        # Fallback: body text scan
        if merge_status == "unknown":
            body_text = await page.inner_text("body")
            lower = body_text.lower()
            if "merged" in lower:
                merge_status = "merged"
            elif "closed" in lower:
                merge_status = "closed"

        # ── PR creator ──────────────────────────────────────────────
        pr_creator = None

        # Primary: .author link in header meta
        el = await page.query_selector(".gh-header-meta .author")
        if el:
            pr_creator = (await el.inner_text()).strip() or None

        # Fallback: first a.author on page
        if not pr_creator:
            el = await page.query_selector("a.author")
            if el:
                pr_creator = (await el.inner_text()).strip() or None

        # ── Approvers — try multiple strategies ─────────────────────
        approvers: list[str] = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // Strategy 1: .review-status-item with approval indicator (mock HTML)
            const items = document.querySelectorAll('.review-status-item');
            for (const item of items) {
                const approved = item.querySelector('.status-approved, .octicon-check');
                if (approved) {
                    const nameEl = item.querySelector('.assignee, a.author, .css-truncate-target');
                    if (nameEl) {
                        const name = nameEl.textContent.trim();
                        if (name && !seen.has(name)) { seen.add(name); results.push(name); }
                    }
                }
            }

            // Strategy 2: sidebar a.assignee links (real GitHub)
            if (results.length === 0) {
                const sidebar = document.querySelector('#partial-discussion-sidebar');
                if (sidebar) {
                    const links = sidebar.querySelectorAll('a.assignee');
                    for (const link of links) {
                        const name = link.textContent.trim();
                        if (name && !seen.has(name)) { seen.add(name); results.push(name); }
                    }
                }
            }

            return results;
        }""")

        # ── Merger ──────────────────────────────────────────────────
        merger = None

        # Primary: look for merge event in timeline via page.evaluate
        merger = await page.evaluate("""() => {
            // Look for "X merged commit" pattern in timeline
            const condensed = document.querySelectorAll(
                '.TimelineItem--condensed, .TimelineItem'
            );
            for (const item of condensed) {
                const text = item.textContent;
                const m = text.match(/(\\w[\\w-]*)\\s+merged\\s+commit/i);
                if (m) return m[1];
            }
            return null;
        }""")

        # Text fallback for creator/merger
        if not pr_creator or not merger:
            text = await page.inner_text("body")
            if not pr_creator:
                m = re.search(r"(\w[\w-]*)\s+wants to merge", text)
                if not m:
                    m = re.search(r"(\w[\w-]*)\s+merged\s+\d+\s+commit", text)
                if m:
                    pr_creator = m.group(1)
            if not merger:
                m = re.search(r"(\w[\w-]*)\s+merged\s+commit", text, re.IGNORECASE)
                if not m:
                    m = re.search(r"(\w[\w-]*)\s+merged\s+\d+\s+commit", text, re.IGNORECASE)
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
        """Extract CI check results from the checks tab page.

        Expects the page to be on the /checks tab (use open_checks() first).
        Returns dict with: check_summary, failed_checks,
        merged_with_failures, checks_raw.
        """
        # Use page.evaluate for robust extraction of check items
        checks_raw: list[dict] = await page.evaluate("""() => {
            const results = [];

            // ── Strategy 1: Real GitHub checks page ──
            // Check runs are div.checks-list-item (not <details> which are suites).
            // Status is in .checks-list-item-icon svg[aria-label].
            const checkRuns = document.querySelectorAll('div.checks-list-item');
            for (const item of checkRuns) {
                const nameEl = item.querySelector('.checks-list-item-name');
                const name = nameEl ? nameEl.textContent.trim() : '';
                if (!name) continue;

                const icon = item.querySelector(
                    '.checks-list-item-icon svg[aria-label]'
                );
                let status = 'unknown';
                if (icon) {
                    const label = (icon.getAttribute('aria-label') || '').toLowerCase();
                    if (label.includes('passed') || label.includes('succeeded')) {
                        status = 'pass';
                    } else if (label.includes('failed') || label.includes('failure')) {
                        status = 'fail';
                    } else if (label.includes('pending') || label.includes('in progress')
                               || label.includes('queued') || label.includes('waiting')) {
                        status = 'pending';
                    } else if (label.includes('skipped') || label.includes('cancelled')
                               || label.includes('neutral')) {
                        status = 'skip';
                    }
                }
                results.push({ name, status, required: true });
            }

            // ── Strategy 2: Mock HTML with merge-status-item / data-check-run-name ──
            if (results.length === 0) {
                const items = document.querySelectorAll(
                    '.merge-status-item[data-check-run-name], [data-check-run-name]'
                );
                for (const item of items) {
                    const name = item.getAttribute('data-check-run-name') || '';
                    const icon = item.querySelector('.status-icon, [class*="octicon"]');
                    let status = 'unknown';
                    if (icon) {
                        const cls = icon.className || '';
                        const text = icon.textContent.trim();
                        if (cls.includes('octicon-check') || text === '✓') {
                            status = 'pass';
                        } else if (cls.includes('octicon-x') || text === '✗') {
                            status = 'fail';
                        } else if (cls.includes('octicon-dot-fill') || text === '●') {
                            status = 'pending';
                        }
                    }
                    const reqEl = item.querySelector('.text-small, .check-required');
                    const reqText = reqEl ? reqEl.textContent.trim().toLowerCase() : '';
                    const required = reqText !== 'optional';
                    if (name) {
                        results.push({ name, status, required });
                    }
                }
            }

            return results;
        }""")

        # Text fallback: parse ✓/✗ markers from body
        if not checks_raw:
            text = await page.inner_text("body")
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
        optional = sum(1 for c in checks_raw if not c.get("required", True))
        check_summary = f"passed={passed}; failed={failed}; pending={pending}; optional={optional}"

        failed_checks = [c["name"] for c in checks_raw if c["status"] == "fail"]

        # Determine merge status from the header (shared across tabs)
        merged = False
        state_el = await page.query_selector(".State")
        if state_el:
            classes = await state_el.get_attribute("class") or ""
            text = (await state_el.inner_text()).strip().lower()
            merged = "State--merged" in classes or text == "merged"

        merged_with_failures = merged and len(failed_checks) > 0

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
        # First .comment-body is the PR description on real GitHub
        desc_el = await page.query_selector(".comment-body")
        if not desc_el:
            desc_el = await page.query_selector(".markdown-body")
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

        Expects the page to be on the Checks tab.
        Returns the href of the details link, or None if not found.
        """
        # Strategy 1: find by data-check-run-name attribute (mock HTML)
        el = await page.query_selector(f"[data-check-run-name='{check_name}']")

        # Strategy 2: find by text content match in real GitHub checks DOM
        if not el:
            el = await page.evaluate_handle(f"""() => {{
                const items = document.querySelectorAll(
                    'div.checks-list-item, .merge-status-item'
                );
                for (const item of items) {{
                    const nameEl = item.querySelector(
                        '.checks-list-item-name, .check-run-name, .check-name'
                    );
                    if (nameEl && nameEl.textContent.trim() === {check_name!r}) {{
                        return item;
                    }}
                }}
                return null;
            }}""")
            el = el.as_element() if el else None

        if not el:
            return None

        # Look for details link within the check item
        link = await el.query_selector("a.details-link")
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
