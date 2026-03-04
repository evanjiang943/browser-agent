"""GitHub checks + CI + Jira traversal playbook runner."""

from __future__ import annotations

import asyncio
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
from evidence_collector.evidence.logging import RunLogger
from evidence_collector.evidence.manifest import RunManifest, SampleNotes, write_manifest
from evidence_collector.evidence.naming import safe_folder_name, screenshot_filename
from evidence_collector.io.csv_utils import write_results_csv
from evidence_collector.io.paths import read_notes, setup_run_dir, setup_sample_dir, write_notes
from evidence_collector.io.spreadsheets import load_github_samples
from evidence_collector.utils.retry import retry_async
from evidence_collector.utils.throttling import CircuitBreaker, Throttle
from evidence_collector.utils.time import now_filename_stamp, now_iso

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

    def load_samples(self) -> list[dict]:
        return load_github_samples(self.input_path)

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

    async def _run_async(self) -> None:
        config = self.config if isinstance(self.config, RunConfig) else RunConfig()
        started_at = now_iso()
        run_id = f"github-checks-{now_filename_stamp()}"

        out_dir = setup_run_dir(self.output_dir, self.playbook_name, run_id)
        run_logger = RunLogger(out_dir)
        evidence_dir = out_dir / "evidence" / self.playbook_name

        browser_adapter = BrowserAdapter(
            profile_dir=Path(config.browser.profile_dir) if config.browser.profile_dir else None,
            headless=config.browser.headless,
            timeout=config.browser.timeout_ms,
        )
        github_adapter = GitHubAdapter(browser_adapter)

        samples = self.load_samples()
        if not samples:
            write_results_csv(out_dir / "results.csv", [])
            run_logger.log("run_end", detail="no samples")
            return

        # Set instance attrs for process_sample
        self._browser_adapter = browser_adapter
        self._github_adapter = github_adapter
        self._evidence_dir = evidence_dir
        self._screenshot_mode = config.screenshot.mode
        self._max_ci_details = _DEFAULT_MAX_CI_DETAILS

        throttle = Throttle(max_per_minute=config.throttle.max_pages_per_minute)
        circuit_breaker = CircuitBreaker(failure_threshold=5, pause_seconds=30.0)
        semaphore = asyncio.Semaphore(config.concurrency)
        total = len(samples)

        async def _process_one(i: int, sample: dict) -> dict:
            sample_id = sample["sample_id"]
            sample_dir = evidence_dir / sample_id

            # Resumability: skip completed samples
            existing_notes = read_notes(sample_dir)
            if existing_notes and existing_notes.get("status") == "success":
                run_logger.log(
                    "sample_skip", sample_id=sample_id, detail="already completed"
                )
                return {col: "" for col in RESULT_COLUMNS} | {
                    "sample_id": sample_id,
                    "github_url": sample["github_url"],
                    "status": "success",
                }

            # Circuit breaker check
            if circuit_breaker.is_open():
                run_logger.log(
                    "circuit_breaker_open",
                    level="WARNING",
                    sample_id=sample_id,
                )
                await asyncio.sleep(30.0)

            async with semaphore:
                await throttle.acquire()
                logger.info("Processing sample %d/%d: %s", i + 1, total, sample_id)
                run_logger.log("sample_start", sample_id=sample_id)

                try:
                    result = await retry_async(
                        lambda s=sample: self.process_sample(s),
                        max_attempts=config.throttle.retry_attempts,
                        backoff_base=config.throttle.backoff_base_seconds,
                        retryable_exceptions=(TimeoutError, ConnectionError),
                    )
                    if result["status"] in ("success", "partial"):
                        circuit_breaker.record_success()
                    else:
                        circuit_breaker.record_failure()
                    run_logger.log(
                        "sample_end",
                        sample_id=sample_id,
                        status=result["status"],
                    )
                    return result
                except Exception as exc:
                    circuit_breaker.record_failure()
                    logger.error(
                        "Sample %s failed after retries: %s",
                        sample_id,
                        exc,
                        exc_info=True,
                    )
                    run_logger.log(
                        "sample_end",
                        sample_id=sample_id,
                        status="failed",
                        level="ERROR",
                        error=str(exc),
                    )
                    return {col: "" for col in RESULT_COLUMNS} | {
                        "sample_id": sample_id,
                        "github_url": sample["github_url"],
                        "status": "failed",
                        "error": str(exc),
                    }

        try:
            results = await asyncio.gather(
                *(_process_one(i, s) for i, s in enumerate(samples))
            )
        finally:
            await browser_adapter.close()

        write_results_csv(out_dir / "results.csv", list(results))
        write_manifest(
            RunManifest(
                run_id=run_id,
                playbook=self.playbook_name,
                input_file=str(self.input_path),
                output_dir=str(out_dir),
                config=config.model_dump(),
                started_at=started_at,
                finished_at=now_iso(),
            ),
            out_dir,
        )
        run_logger.log("run_end", detail="complete")

    def run(self) -> None:
        asyncio.run(self._run_async())
