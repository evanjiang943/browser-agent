"""Code recency + materiality (blame) playbook runner."""

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
from evidence_collector.evidence.naming import screenshot_filename
from evidence_collector.io.csv_utils import write_results_csv
from evidence_collector.io.paths import read_notes, setup_run_dir, setup_sample_dir, write_notes
from evidence_collector.io.spreadsheets import load_code_recency_samples
from evidence_collector.utils.retry import retry_async
from evidence_collector.utils.throttling import CircuitBreaker, Throttle
from evidence_collector.utils.time import is_within_window, now_filename_stamp, now_iso

from .base import BaseRunner

logger = logging.getLogger(__name__)

# Heuristic threshold for materiality: trivial if total changes <= this
_TRIVIAL_CHANGE_THRESHOLD = 5

RESULT_COLUMNS = [
    "sample_id",
    "repo_url",
    "file_path",
    "snippet_hash",
    "last_change_date",
    "commit_sha",
    "commit_url",
    "within_window",
    "material_change_flag",
    "rationale",
    "status",
    "error",
]


class CodeRecencyRunner(BaseRunner):
    """Playbook D: git blame analysis for code snippet recency and materiality."""

    @property
    def playbook_name(self) -> str:
        return "code-recency"

    def load_samples(self) -> list[dict]:
        return load_code_recency_samples(self.input_path)

    async def process_sample(self, sample: dict) -> dict:
        sample_id = sample["sample_id"]
        repo_url = sample["repo_url"]
        code_string = sample["code_string"]
        time_window_days = sample.get("time_window_days", 365)

        sample_dir = setup_sample_dir(self._evidence_dir, sample_id)
        screenshots_dir = sample_dir / "screenshots"

        notes = SampleNotes(sample_id=sample_id, status="pending")
        result = {col: "" for col in RESULT_COLUMNS}
        result["sample_id"] = sample_id
        result["repo_url"] = repo_url
        result["snippet_hash"] = sample_id

        try:
            # Step 1: search_code — find file containing snippet
            try:
                search_result = await self._github_adapter.search_code(
                    repo_url, code_string
                )
            except LoginRedirectError:
                notes.status = "failed"
                notes.errors.append("AUTH_REQUIRED")
                result["status"] = "failed"
                result["error"] = "AUTH_REQUIRED"
                return result
            except PageNotFoundError:
                notes.status = "failed"
                notes.errors.append("SEARCH_PAGE_NOT_FOUND")
                result["status"] = "failed"
                result["error"] = "SEARCH_PAGE_NOT_FOUND"
                return result

            if search_result is None:
                notes.status = "failed"
                notes.errors.append("CODE_NOT_FOUND")
                result["status"] = "failed"
                result["error"] = "CODE_NOT_FOUND"
                return result

            file_url, line_range = search_result
            result["file_path"] = file_url
            notes.steps_completed.append("search_code")
            write_notes(sample_dir, notes.model_dump())

            # Step 2: screenshot the file view
            try:
                file_page = await self._browser_adapter.open(file_url)
            except (LoginRedirectError, PageNotFoundError) as exc:
                notes.status = "failed"
                notes.errors.append(f"FILE_OPEN_ERROR:{exc}")
                result["status"] = "failed"
                result["error"] = str(exc)
                return result

            fname = screenshot_filename(sample_id, "github", "file_view")
            await self._browser_adapter.screenshot(
                file_page, screenshots_dir / fname, mode=self._screenshot_mode
            )
            notes.screenshots.append(fname)
            notes.steps_completed.append("screenshot_file_view")
            write_notes(sample_dir, notes.model_dump())
            await file_page.close()

            # Step 3: open_blame_view
            try:
                blame_page = await self._github_adapter.open_blame_view(file_url)
            except (LoginRedirectError, PageNotFoundError) as exc:
                notes.status = "failed"
                notes.errors.append(f"BLAME_ERROR:{exc}")
                result["status"] = "failed"
                result["error"] = str(exc)
                return result

            notes.steps_completed.append("open_blame_view")
            write_notes(sample_dir, notes.model_dump())

            # Step 4: screenshot blame view
            fname = screenshot_filename(sample_id, "github", "blame_view")
            await self._browser_adapter.screenshot(
                blame_page, screenshots_dir / fname, mode=self._screenshot_mode
            )
            notes.screenshots.append(fname)
            notes.steps_completed.append("screenshot_blame_view")
            write_notes(sample_dir, notes.model_dump())

            # Step 5: extract_blame_dates
            blame_dates = await self._github_adapter.extract_blame_dates(
                blame_page, line_range
            )
            await blame_page.close()
            notes.steps_completed.append("extract_blame_dates")
            write_notes(sample_dir, notes.model_dump())

            if not blame_dates:
                notes.status = "partial"
                notes.errors.append("NO_BLAME_DATA")
                result["status"] = "partial"
                result["error"] = "NO_BLAME_DATA"
                result["within_window"] = ""
                result["material_change_flag"] = ""
                result["rationale"] = "Could not extract blame dates"
                return result

            # Find the most recent blame entry
            most_recent = max(blame_dates, key=lambda d: d.get("date", ""))
            last_date = most_recent.get("date", "")
            last_sha = most_recent.get("sha", "")
            result["last_change_date"] = last_date
            result["commit_sha"] = last_sha

            # Step 6: is_within_window check
            if last_date:
                within = is_within_window(last_date, time_window_days)
            else:
                within = False
            result["within_window"] = str(within)
            notes.steps_completed.append("check_window")
            write_notes(sample_dir, notes.model_dump())

            # Step 7 / 8: materiality assessment
            if within and last_sha:
                # Open commit page, screenshot, extract diff summary
                commit_url = f"{repo_url.rstrip('/')}/commit/{last_sha}"
                result["commit_url"] = commit_url

                try:
                    commit_page = await self._browser_adapter.open(commit_url)
                    try:
                        fname = screenshot_filename(
                            sample_id, "github", "commit"
                        )
                        await self._browser_adapter.screenshot(
                            commit_page,
                            screenshots_dir / fname,
                            mode=self._screenshot_mode,
                        )
                        notes.screenshots.append(fname)

                        diff_summary = (
                            await self._github_adapter.extract_commit_diff_summary(
                                commit_page
                            )
                        )

                        total_changes = (
                            diff_summary["lines_added"]
                            + diff_summary["lines_removed"]
                        )
                        material = total_changes > _TRIVIAL_CHANGE_THRESHOLD
                        result["material_change_flag"] = str(material)

                        if material:
                            result["rationale"] = (
                                f"Within window; {diff_summary['files_changed']} files, "
                                f"+{diff_summary['lines_added']}"
                                f"/-{diff_summary['lines_removed']} lines"
                            )
                        else:
                            result["rationale"] = (
                                f"Within window but trivial change "
                                f"({total_changes} lines)"
                            )
                    finally:
                        await commit_page.close()
                except Exception as exc:
                    logger.warning(
                        "Commit page failed for %s: %s", last_sha, exc
                    )
                    notes.errors.append(f"COMMIT_ERROR:{exc}")
                    result["material_change_flag"] = "unknown"
                    result["rationale"] = f"Could not assess: {exc}"

                notes.steps_completed.append("materiality_assessment")
            else:
                result["material_change_flag"] = "False"
                result["rationale"] = (
                    "Outside time window; code is stable"
                    if last_date
                    else "No date data; cannot determine recency"
                )
                notes.steps_completed.append("materiality_assessment")

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
        run_id = f"code-recency-{now_filename_stamp()}"

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
                    "repo_url": sample["repo_url"],
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
                        "repo_url": sample["repo_url"],
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
