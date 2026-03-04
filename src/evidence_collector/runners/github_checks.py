"""GitHub checks + CI + Jira traversal playbook runner."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from evidence_collector.adapters.browser import (
    BrowserAdapter,
    LoginRedirectError,
    PageNotFoundError,
)
from evidence_collector.adapters.github import GitHubAdapter
from evidence_collector.config import RunConfig
from evidence_collector.evidence.manifest import SampleNotes
from evidence_collector.evidence.naming import safe_folder_name, screenshot_filename
from evidence_collector.io.paths import setup_sample_dir, write_notes
from evidence_collector.io.spreadsheets import load_github_samples

from .base import PlaybookRunner

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CI_DETAILS = 3

RESULT_COLUMNS = [
    "sample_id",
    "github_url",
    "pr_or_commit_id",
    "pr_creator",
    "approvers",
    "merger",
    "merge_status",
    "title",
    "check_summary",
    "failed_checks_notes",
    "jira_url",
    "status",
    "error",
]


class GitHubChecksRunner(PlaybookRunner):
    """Playbook B: PR/commit evidence with checks, CI, and Jira traversal."""

    @property
    def playbook_name(self) -> str:
        return "github-checks"

    @property
    def result_columns(self) -> list[str]:
        return RESULT_COLUMNS

    def load_samples(self) -> list[dict]:
        return load_github_samples(self.input_path)

    def create_adapters(self, config: RunConfig, browser_adapter: BrowserAdapter) -> None:
        self._github_adapter = GitHubAdapter(browser_adapter)
        self._max_ci_details = _DEFAULT_MAX_CI_DETAILS

    async def process_sample(self, sample: dict) -> dict:
        sample_id = sample["sample_id"]
        github_url = sample["github_url"]

        sample_dir = setup_sample_dir(self._evidence_dir, sample_id)
        screenshots_dir = sample_dir / "screenshots"

        notes = SampleNotes(sample_id=sample_id, status="pending")
        result = {col: "" for col in RESULT_COLUMNS}
        result["sample_id"] = sample_id
        result["github_url"] = github_url

        try:
            # Step 1: open_primary_page
            try:
                page = await self._browser_adapter.open(github_url)
            except LoginRedirectError:
                notes.status = "failed"
                notes.errors.append("AUTH_REQUIRED")
                result["status"] = "failed"
                result["error"] = "AUTH_REQUIRED"
                return result
            except PageNotFoundError:
                notes.status = "failed"
                notes.errors.append("PAGE_NOT_FOUND")
                result["status"] = "failed"
                result["error"] = "PAGE_NOT_FOUND"
                return result

            notes.steps_completed.append("open_primary_page")
            write_notes(sample_dir, notes.model_dump())

            # Step 2: screenshot_pr_page
            fname = screenshot_filename(sample_id, "github", "pr_page")
            shot_path = screenshots_dir / fname
            await self._browser_adapter.screenshot(
                page, shot_path, mode=self._screenshot_mode
            )
            notes.screenshots.append(fname)
            notes.steps_completed.append("screenshot_pr_page")
            write_notes(sample_dir, notes.model_dump())

            # Step 3: extract_metadata
            meta = await self._github_adapter.extract_pr_metadata(page)
            result["title"] = meta.get("title") or ""
            result["pr_or_commit_id"] = meta.get("pr_or_commit_id") or ""
            result["pr_creator"] = meta.get("pr_creator") or ""
            result["approvers"] = ";".join(meta.get("approvers") or [])
            result["merger"] = meta.get("merger") or ""
            result["merge_status"] = meta.get("merge_status") or ""
            notes.steps_completed.append("extract_metadata")
            write_notes(sample_dir, notes.model_dump())

            # Step 4: screenshot_checks
            checks_section = await page.query_selector("[data-section='checks']")
            if checks_section:
                await checks_section.scroll_into_view_if_needed()
            fname = screenshot_filename(sample_id, "github", "checks")
            shot_path = screenshots_dir / fname
            await self._browser_adapter.screenshot(
                page, shot_path, mode=self._screenshot_mode
            )
            notes.screenshots.append(fname)
            notes.steps_completed.append("screenshot_checks")
            write_notes(sample_dir, notes.model_dump())

            # Step 5: extract_checks
            checks = await self._github_adapter.extract_checks(page)
            result["check_summary"] = checks.get("check_summary", "")
            failed_checks = checks.get("failed_checks", [])
            result["failed_checks_notes"] = ";".join(failed_checks)
            result["merged_with_failures"] = checks.get("merged_with_failures", False)
            notes.steps_completed.append("extract_checks")
            write_notes(sample_dir, notes.model_dump())

            # Step 6: ci_details
            for ci_check in failed_checks[: self._max_ci_details]:
                try:
                    details_url = await self._github_adapter.get_ci_details_url(
                        ci_check, page
                    )
                    if not details_url:
                        continue
                    ci_page = await self._browser_adapter.open(details_url)
                    try:
                        safe_name = safe_folder_name(ci_check)
                        fname = screenshot_filename(
                            sample_id, "github", f"ci_{safe_name}"
                        )
                        await self._browser_adapter.screenshot(
                            ci_page,
                            screenshots_dir / fname,
                            mode="viewport",
                        )
                        notes.screenshots.append(fname)
                        # Scroll to logs region and take second screenshot
                        await ci_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await ci_page.wait_for_timeout(200)
                        fname2 = screenshot_filename(
                            sample_id, "github", f"ci_{safe_name}_logs"
                        )
                        await self._browser_adapter.screenshot(
                            ci_page,
                            screenshots_dir / fname2,
                            mode="viewport",
                        )
                        notes.screenshots.append(fname2)
                    finally:
                        await ci_page.close()
                except Exception as exc:
                    logger.warning("CI details failed for %s: %s", ci_check, exc)
                    notes.errors.append(f"CI_DETAILS_ERROR:{ci_check}")
            notes.steps_completed.append("ci_details")
            write_notes(sample_dir, notes.model_dump())

            # Step 7: jira_traversal
            ticket_links = await self._github_adapter.find_ticket_links(page)
            result["jira_url"] = ";".join(ticket_links)

            if ticket_links:
                first_link = ticket_links[0]
                try:
                    jira_page = await self._browser_adapter.open(first_link)
                    try:
                        linked_dir = sample_dir / "linked" / "jira"
                        linked_dir.mkdir(parents=True, exist_ok=True)
                        fname = screenshot_filename(sample_id, "jira", "ticket")
                        await self._browser_adapter.screenshot(
                            jira_page,
                            linked_dir / fname,
                            mode=self._screenshot_mode,
                        )
                        notes.screenshots.append(fname)
                    finally:
                        await jira_page.close()
                except LoginRedirectError:
                    logger.warning("Jira auth required for %s", first_link)
                    notes.errors.append("JIRA_AUTH_REQUIRED")
                except Exception as exc:
                    logger.warning("Jira traversal failed: %s", exc)
                    notes.errors.append(f"JIRA_ERROR:{exc}")

            notes.steps_completed.append("jira_traversal")
            write_notes(sample_dir, notes.model_dump())

            # Final status
            if notes.errors:
                notes.status = "partial"
                result["status"] = "partial"
                result["error"] = ";".join(notes.errors)
            else:
                notes.status = "success"
                result["status"] = "success"

        except Exception as exc:
            logger.error("Sample %s failed: %s", sample_id, exc, exc_info=True)
            notes.status = "failed"
            notes.errors.append(str(exc))
            result["status"] = "failed"
            result["error"] = str(exc)
        finally:
            write_notes(sample_dir, notes.model_dump())

        return result

