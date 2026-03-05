"""AgentRunner — orchestrates the agent loop across samples with concurrency."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from evidence_collector.adapters.browser import BrowserAdapter
from evidence_collector.agent.loop import AgentContext, run_agent_for_sample
from evidence_collector.agent.report import generate_run_report, generate_sample_report
from evidence_collector.agent.task import TaskDescription
from evidence_collector.config import RunConfig
from evidence_collector.evidence.logging import RunLogger
from evidence_collector.evidence.manifest import RunManifest, SampleNotes, write_manifest
from evidence_collector.evidence.naming import generate_sample_id
from evidence_collector.io.csv_utils import write_results_csv
from evidence_collector.io.paths import read_notes, setup_run_dir, setup_sample_dir, write_notes
from evidence_collector.io.spreadsheets import read_input, validate_columns
from evidence_collector.utils.retry import retry_async
from evidence_collector.utils.throttling import CircuitBreaker, Throttle
from evidence_collector.utils.time import now_filename_stamp, now_iso

logger = logging.getLogger(__name__)


class AgentRunner:
    """Runs the LLM agent for each sample in the input file."""

    def __init__(
        self,
        task: TaskDescription,
        input_path: Path,
        output_dir: Path,
        config: RunConfig | None = None,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        self.task = task
        self.input_path = input_path
        self.output_dir = output_dir
        self.config = config or RunConfig()
        self.on_progress = on_progress

    def _load_samples(self) -> list[dict]:
        """Load and validate samples from the input file."""
        rows = read_input(self.input_path)
        missing = validate_columns(rows, self.task.input_columns)
        if missing:
            raise ValueError(
                f"Input file is missing required columns: {', '.join(missing)}"
            )

        # Add sample_id to each row
        for row in rows:
            if "sample_id" not in row:
                # Try exact column names first, then fall back to any URL-like column
                pk = row.get("primary_key")
                url = row.get("url")
                name = row.get("name")
                if not pk and not url and not name:
                    # Look for any column ending in _url or containing a URL value
                    for col, val in row.items():
                        if isinstance(val, str) and (col.endswith("_url") or val.startswith("http")):
                            url = val
                            break
                if not pk and not url and not name:
                    # Last resort: use the first non-empty string value
                    for val in row.values():
                        if isinstance(val, str) and val.strip():
                            name = val
                            break
                row["sample_id"] = generate_sample_id(
                    primary_key=pk, url=url, name=name,
                )
        return rows

    def _create_client(self) -> Any:
        """Create an Anthropic API client."""
        import anthropic

        api_key = os.environ.get(self.config.agent.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"API key not found. Set the {self.config.agent.api_key_env} environment variable."
            )
        return anthropic.AsyncAnthropic(api_key=api_key)

    async def _run_async(self) -> None:
        """Main orchestration loop."""
        config = self.config
        started_at = now_iso()
        run_id = f"{self.task.task_name}-{now_filename_stamp()}"

        out_dir = setup_run_dir(self.output_dir, self.task.task_name, run_id)
        run_logger = RunLogger(out_dir)
        evidence_dir = out_dir / "evidence" / self.task.task_name

        browser_adapter = BrowserAdapter(
            profile_dir=Path(config.browser.profile_dir) if config.browser.profile_dir else None,
            headless=config.browser.headless,
            timeout=config.browser.timeout_ms,
        )

        client = self._create_client()

        samples = self._load_samples()
        if not samples:
            write_results_csv(out_dir / "results.csv", [])
            run_logger.log("run_end", detail="no samples")
            return

        result_cols = ["sample_id", "status", "error"] + [
            f.name for f in self.task.output_schema
        ]

        throttle = Throttle(max_per_minute=config.throttle.max_pages_per_minute)
        circuit_breaker = CircuitBreaker(failure_threshold=5, pause_seconds=30.0)
        semaphore = asyncio.Semaphore(config.concurrency)
        total = len(samples)

        async def _process_one(i: int, sample: dict) -> dict:
            sample_id = sample["sample_id"]
            sample_dir = setup_sample_dir(evidence_dir, sample_id)

            # Resumability: skip completed samples
            existing_notes = read_notes(sample_dir)
            if existing_notes and existing_notes.get("status") == "success":
                run_logger.log(
                    "sample_skip", sample_id=sample_id, detail="already completed"
                )
                result = existing_notes.get("result_data", {})
                result["sample_id"] = sample_id
                result["status"] = "success"
                return result

            # Circuit breaker check
            if circuit_breaker.is_open():
                run_logger.log(
                    "circuit_breaker_open", level="WARNING", sample_id=sample_id
                )
                await asyncio.sleep(30.0)

            async with semaphore:
                await throttle.acquire()
                logger.info("Processing sample %d/%d: %s", i + 1, total, sample_id)
                run_logger.log("sample_start", sample_id=sample_id)

                # Build notes (restore if resuming)
                notes = SampleNotes(sample_id=sample_id, status="pending")
                if existing_notes:
                    notes = SampleNotes.model_validate(existing_notes)
                    notes.status = "pending"

                ctx = AgentContext(
                    sample_id=sample_id,
                    input=sample,
                    task=self.task,
                    sample_dir=sample_dir,
                    browser=browser_adapter,
                    run_logger=run_logger,
                    config=config.agent,
                    screenshot_mode=config.screenshot.mode,
                    notes=notes,
                    on_progress=self.on_progress,
                )

                if self.on_progress:
                    try:
                        await self.on_progress({
                            "event_type": "sample_start",
                            "sample_id": sample_id,
                            "sample_index": i,
                            "total_samples": total,
                        })
                    except Exception:
                        pass

                try:
                    import anthropic as _anthropic

                    recorded = await retry_async(
                        lambda c=ctx: run_agent_for_sample(c, client),
                        max_attempts=config.throttle.retry_attempts,
                        backoff_base=config.throttle.backoff_base_seconds,
                        retryable_exceptions=(
                            TimeoutError,
                            ConnectionError,
                            _anthropic.RateLimitError,
                        ),
                    )
                    status = ctx.notes.status
                    if status in ("success", "partial"):
                        circuit_breaker.record_success()
                    else:
                        circuit_breaker.record_failure()

                    # Generate per-sample audit report
                    try:
                        generate_sample_report(sample_dir)
                    except Exception:
                        logger.warning("Failed to generate report for %s", sample_id, exc_info=True)

                    result = {"sample_id": sample_id, "status": status}
                    result.update(recorded)
                    if self.on_progress:
                        try:
                            await self.on_progress({
                                "event_type": "sample_end",
                                "sample_id": sample_id,
                                "sample_index": i,
                                "total_samples": total,
                                "status": status,
                            })
                        except Exception:
                            pass
                    run_logger.log(
                        "sample_end", sample_id=sample_id, status=status
                    )
                    return result
                except Exception as exc:
                    circuit_breaker.record_failure()
                    logger.error(
                        "Sample %s failed after retries: %s",
                        sample_id, exc, exc_info=True,
                    )
                    run_logger.log(
                        "sample_end", sample_id=sample_id,
                        status="failed", level="ERROR", error=str(exc),
                    )
                    result = {col: "" for col in result_cols}
                    result["sample_id"] = sample_id
                    result["status"] = "failed"
                    result["error"] = str(exc)
                    return result

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
                playbook=self.task.task_name,
                input_file=str(self.input_path),
                output_dir=str(out_dir),
                config=config.model_dump(),
                started_at=started_at,
                finished_at=now_iso(),
            ),
            out_dir,
        )

        # Generate run-level audit report
        try:
            generate_run_report(out_dir, self.task.task_name)
        except Exception:
            logger.warning("Failed to generate run report", exc_info=True)

        run_logger.log("run_end", detail="complete")

    def run(self) -> None:
        """Run the full agent pipeline across all samples."""
        asyncio.run(self._run_async())
