"""Generic step-based runner and legacy abstract base class."""

from __future__ import annotations

import abc
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from evidence_collector.adapters.browser import BrowserAdapter
from evidence_collector.config import RunConfig
from evidence_collector.evidence.logging import RunLogger
from evidence_collector.evidence.manifest import RunManifest, SampleNotes, SubItemNotes, write_manifest
from evidence_collector.evidence.naming import generate_sample_id, screenshot_filename
from evidence_collector.io.csv_utils import write_results_csv
from evidence_collector.io.paths import read_notes, setup_run_dir, setup_sample_dir, write_notes
from evidence_collector.utils.retry import retry_async
from evidence_collector.utils.throttling import CircuitBreaker, Throttle
from evidence_collector.utils.time import now_filename_stamp, now_iso

logger = logging.getLogger(__name__)


# ── Step runner primitives ──────────────────────────────────────────────


class StepFailed(Exception):
    """Raised by SampleContext.fail() to abort the current step."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        self.message = message
        super().__init__(f"{error_code}: {message}" if message else error_code)


@dataclass
class StepDefinition:
    """Declarative step in a playbook pipeline.

    *fn* receives a :class:`SampleContext` and performs one logical action
    (navigate, extract, screenshot, etc.).  If *required* is False, a failure
    marks the sample as ``partial`` instead of ``failed``.
    """

    name: str
    fn: Callable[["SampleContext"], Awaitable[None]]
    required: bool = True
    max_retries: int = 0


class SampleContext:
    """Mutable context threaded through every step of a sample."""

    def __init__(
        self,
        sample_id: str,
        input: dict,
        evidence_dir: Path,
        browser: BrowserAdapter,
        logger: RunLogger,
        screenshot_mode: str = "viewport",
    ) -> None:
        self.sample_id = sample_id
        self.input = input
        self.state: dict[str, Any] = {}
        self.evidence_dir = evidence_dir
        self.sample_dir = setup_sample_dir(evidence_dir, sample_id)
        self.browser = browser
        self.logger = logger
        self.screenshot_mode = screenshot_mode
        self._notes = SampleNotes(sample_id=sample_id, status="pending")

    # ── Convenience helpers ─────────────────────────────────────────

    async def screenshot(
        self,
        page: Any,
        step_name: str,
        system: str = "web",
        mode: str | None = None,
    ) -> list[Path]:
        """Take a screenshot, register it in notes, return paths."""
        screenshots_dir = self.sample_dir / "screenshots"
        fname = screenshot_filename(self.sample_id, system, step_name)
        shot_path = screenshots_dir / fname
        await self.browser.screenshot(page, shot_path, mode=mode or self.screenshot_mode)
        self._notes.screenshots.append(fname)
        return [shot_path]

    async def save_file(self, data: bytes, filename: str) -> Path:
        """Save arbitrary bytes to the downloads directory."""
        dest = self.sample_dir / "downloads" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        self._notes.downloads.append(filename)
        return dest

    def record(self, **kwargs: Any) -> None:
        """Merge key-value pairs into state (used for CSV output)."""
        self.state.update(kwargs)

    def fail(self, error_code: str, message: str = "") -> None:
        """Record an error and abort the current step."""
        raise StepFailed(error_code, message)

    # ── Sub-item support ─────────────────────────────────────────────

    def sub_item(self, sub_id: str) -> "SubItemContext":
        """Create or resume a :class:`SubItemContext` for *sub_id*.

        The sub-item's evidence lives under
        ``<sample_dir>/sub_items/<sub_id>/`` and its state is persisted
        inside the parent's ``notes.json`` under ``sub_items.<sub_id>``.
        """
        if sub_id not in self._notes.sub_items:
            self._notes.sub_items[sub_id] = SubItemNotes()
        sub_notes = self._notes.sub_items[sub_id]

        sub_evidence = self.sample_dir / "sub_items" / sub_id
        sub_evidence.mkdir(parents=True, exist_ok=True)
        (sub_evidence / "screenshots").mkdir(exist_ok=True)

        return SubItemContext(
            sub_id=sub_id,
            parent=self,
            evidence_dir=sub_evidence,
            _sub_notes=sub_notes,
        )

    def completed_sub_items(self) -> set[str]:
        """Return sub_ids where status == ``'success'``."""
        return {
            sid
            for sid, notes in self._notes.sub_items.items()
            if notes.status == "success"
        }

    def all_sub_item_states(self) -> list[dict]:
        """Return list of all sub-item state dicts (for compiling results)."""
        return [
            {"sub_id": sid, **notes.state}
            for sid, notes in self._notes.sub_items.items()
        ]

    def flush_notes(self) -> None:
        """Persist current notes.json immediately (crash-safe sub-item progress)."""
        write_notes(self.sample_dir, self._notes.model_dump())


class SubItemContext:
    """Context for a single sub-item within a sample.

    Created via :meth:`SampleContext.sub_item`.  Screenshots and
    downloads go into a dedicated sub-directory; state is persisted
    in the parent's ``notes.json``.
    """

    def __init__(
        self,
        sub_id: str,
        parent: SampleContext,
        evidence_dir: Path,
        _sub_notes: SubItemNotes,
    ) -> None:
        self.sub_id = sub_id
        self.parent = parent
        self.evidence_dir = evidence_dir
        self.state = _sub_notes.state
        self._sub_notes = _sub_notes

    async def screenshot(
        self,
        page: Any,
        step_name: str,
        system: str = "web",
        mode: str | None = None,
    ) -> list[Path]:
        """Take a screenshot, stored under the sub-item's evidence dir."""
        screenshots_dir = self.evidence_dir / "screenshots"
        fname = screenshot_filename(self.sub_id, system, step_name)
        shot_path = screenshots_dir / fname
        await self.parent.browser.screenshot(
            page, shot_path, mode=mode or self.parent.screenshot_mode
        )
        self._sub_notes.screenshots.append(fname)
        return [shot_path]

    def record(self, **kwargs: Any) -> None:
        """Merge key-value pairs into this sub-item's state."""
        self.state.update(kwargs)

    def fail(self, error_code: str, message: str = "") -> None:
        """Mark sub-item as failed and raise :class:`StepFailed`."""
        self._sub_notes.errors.append(error_code)
        self._sub_notes.status = "failed"
        raise StepFailed(error_code, message)

    def mark_success(self) -> None:
        """Mark this sub-item as successfully completed."""
        self._sub_notes.status = "success"

    def mark_failed(self, error: str) -> None:
        """Mark this sub-item as failed with *error* (without raising)."""
        self._sub_notes.errors.append(error)
        self._sub_notes.status = "failed"


# ── Generic step runner ─────────────────────────────────────────────────


class BaseRunner:
    """Concrete, generic step-based sample runner.

    Executes a list of :class:`StepDefinition` objects for each sample,
    providing for free: resumability, per-step notes persistence, error
    handling with required/optional step distinction, concurrency,
    throttling, circuit breaking, retries, and results.csv construction.
    """

    def __init__(
        self,
        steps: list[StepDefinition],
        result_schema: list[str],
        browser: BrowserAdapter,
        logger: RunLogger,
        evidence_dir: Path,
        config: Any = None,
    ) -> None:
        self.steps = steps
        self.result_schema = result_schema
        self.browser = browser
        self.run_logger = logger
        self.evidence_dir = evidence_dir
        self.config = config

        self._screenshot_mode = "viewport"
        if config is not None:
            from evidence_collector.config import RunConfig

            if isinstance(config, RunConfig):
                self._screenshot_mode = config.screenshot.mode

    # ── Single-sample execution ─────────────────────────────────────

    async def run_sample(self, sample: dict) -> dict:
        """Execute all steps for one sample.  Returns a result dict."""
        sample_id = sample.get("sample_id", "unknown")

        ctx = SampleContext(
            sample_id=sample_id,
            input=sample,
            evidence_dir=self.evidence_dir,
            browser=self.browser,
            logger=self.run_logger,
            screenshot_mode=self._screenshot_mode,
        )

        # Resumability: load existing notes and skip completed steps
        existing_notes = read_notes(ctx.sample_dir)
        completed_steps: set[str] = set()
        if existing_notes:
            completed_steps = set(existing_notes.get("steps_completed", []))
            # Restore notes state so new steps append correctly
            raw_sub_items = existing_notes.get("sub_items", {})
            restored_sub_items = {
                sid: SubItemNotes(**data) for sid, data in raw_sub_items.items()
            }
            ctx._notes = SampleNotes(
                sample_id=sample_id,
                status="pending",
                steps_completed=list(existing_notes.get("steps_completed", [])),
                errors=list(existing_notes.get("errors", [])),
                screenshots=list(existing_notes.get("screenshots", [])),
                downloads=list(existing_notes.get("downloads", [])),
                sub_items=restored_sub_items,
            )
            if existing_notes.get("status") == "success":
                result = existing_notes.get("result_data", {})
                if result:
                    return result
                # Fallback for old notes without result_data
                result = {col: "" for col in self.result_schema}
                result["sample_id"] = sample_id
                result["status"] = "success"
                return result

        has_optional_failure = False

        for step in self.steps:
            if step.name in completed_steps:
                continue

            try:
                await step.fn(ctx)
                ctx._notes.steps_completed.append(step.name)
                write_notes(ctx.sample_dir, ctx._notes.model_dump())
            except StepFailed as e:
                ctx._notes.errors.append(e.error_code)
                if step.required:
                    ctx._notes.status = "failed"
                    write_notes(ctx.sample_dir, ctx._notes.model_dump())
                    return self._build_result(ctx, status="failed", error=e.error_code)
                else:
                    has_optional_failure = True
                    ctx._notes.steps_completed.append(step.name)
                    write_notes(ctx.sample_dir, ctx._notes.model_dump())
            except Exception as exc:
                ctx._notes.errors.append(str(exc))
                if step.required:
                    ctx._notes.status = "failed"
                    write_notes(ctx.sample_dir, ctx._notes.model_dump())
                    return self._build_result(ctx, status="failed", error=str(exc))
                else:
                    has_optional_failure = True
                    ctx._notes.steps_completed.append(step.name)
                    write_notes(ctx.sample_dir, ctx._notes.model_dump())

        # All steps done
        if has_optional_failure or ctx._notes.errors:
            ctx._notes.status = "partial"
        else:
            ctx._notes.status = "success"
        result = self._build_result(ctx)
        ctx._notes.result_data = result
        write_notes(ctx.sample_dir, ctx._notes.model_dump())
        return result

    # ── Batch execution with concurrency ────────────────────────────

    async def run_all(
        self,
        samples: list[dict],
        concurrency: int = 1,
        max_pages_per_minute: int = 20,
        retry_attempts: int = 3,
        backoff_base: float = 2.0,
    ) -> list[dict]:
        """Process all samples with concurrency, throttling, and circuit breaking."""
        if not samples:
            return []

        throttle = Throttle(max_per_minute=max_pages_per_minute)
        circuit_breaker = CircuitBreaker(failure_threshold=5, pause_seconds=30.0)
        semaphore = asyncio.Semaphore(concurrency)
        total = len(samples)

        async def _process_one(i: int, sample: dict) -> dict:
            sample_id = sample.get("sample_id", f"sample-{i}")

            # Quick resumability check before acquiring semaphore
            sample_dir = self.evidence_dir / sample_id
            existing = read_notes(sample_dir)
            if existing and existing.get("status") == "success":
                self.run_logger.log(
                    "sample_skip", sample_id=sample_id, detail="already completed"
                )
                result = existing.get("result_data", {})
                if not result:
                    result = {col: "" for col in self.result_schema}
                    result["sample_id"] = sample_id
                    result["status"] = "success"
                return result

            if circuit_breaker.is_open():
                self.run_logger.log(
                    "circuit_breaker_open", level="WARNING", sample_id=sample_id
                )
                await asyncio.sleep(30.0)

            async with semaphore:
                await throttle.acquire()
                logger.info("Processing sample %d/%d: %s", i + 1, total, sample_id)
                self.run_logger.log("sample_start", sample_id=sample_id)

                try:
                    result = await retry_async(
                        lambda s=sample: self.run_sample(s),
                        max_attempts=retry_attempts,
                        backoff_base=backoff_base,
                        retryable_exceptions=(TimeoutError, ConnectionError),
                    )
                    if result.get("status") in ("success", "partial"):
                        circuit_breaker.record_success()
                    else:
                        circuit_breaker.record_failure()
                    self.run_logger.log(
                        "sample_end",
                        sample_id=sample_id,
                        status=result.get("status", "unknown"),
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
                    self.run_logger.log(
                        "sample_end",
                        sample_id=sample_id,
                        status="failed",
                        level="ERROR",
                        error=str(exc),
                    )
                    result = {col: "" for col in self.result_schema}
                    result["sample_id"] = sample_id
                    result["status"] = "failed"
                    result["error"] = str(exc)
                    return result

        results = await asyncio.gather(
            *(_process_one(i, s) for i, s in enumerate(samples))
        )
        return list(results)

    # ── Internal helpers ────────────────────────────────────────────

    def _build_result(
        self,
        ctx: SampleContext,
        status: str | None = None,
        error: str | None = None,
    ) -> dict:
        """Construct result dict from context state and result_schema."""
        result = {col: "" for col in self.result_schema}
        for k, v in ctx.state.items():
            if k in result:
                result[k] = v
        result["sample_id"] = ctx.sample_id
        result["status"] = status or ctx._notes.status
        if error:
            result["error"] = error
        elif ctx._notes.errors:
            result["error"] = ";".join(ctx._notes.errors)
        return result


# ── Legacy abstract base class ──────────────────────────────────────────


class PlaybookRunner(abc.ABC):
    """Abstract base class for playbook runners.

    Provides shared ``_run_async()`` orchestration: config init, run dir
    creation, adapter setup, throttle/semaphore/circuit-breaker, the
    ``_process_one`` loop (calling ``self.process_sample``), results CSV
    + manifest writing, and browser cleanup.

    Subclasses must implement:
    - ``playbook_name`` — slug for directory paths
    - ``result_columns`` — list of CSV column names
    - ``load_samples()`` — parse input CSV/XLSX
    - ``process_sample(sample)`` — process one sample
    - ``create_adapters(config, browser_adapter)`` — set up adapters on self
    """

    def __init__(self, input_path: Path, output_dir: Path, config: Any) -> None:
        self.input_path = input_path
        self.output_dir = output_dir
        self.config = config

    @property
    @abc.abstractmethod
    def playbook_name(self) -> str:
        """Return the playbook slug used in directory paths."""
        ...

    @property
    @abc.abstractmethod
    def result_columns(self) -> list[str]:
        """Return the list of CSV result column names."""
        ...

    @abc.abstractmethod
    def load_samples(self) -> list[dict]:
        """Load and validate input samples from CSV/XLSX."""
        ...

    @abc.abstractmethod
    async def process_sample(self, sample: dict) -> dict:
        """Process a single sample: navigate, screenshot, extract, write evidence."""
        ...

    @abc.abstractmethod
    def create_adapters(self, config: RunConfig, browser_adapter: BrowserAdapter) -> None:
        """Create playbook-specific adapters and set them on self."""
        ...

    async def _run_async(self) -> None:
        """Shared orchestration for all PlaybookRunner subclasses."""
        config = self.config if isinstance(self.config, RunConfig) else RunConfig()
        started_at = now_iso()
        run_id = f"{self.playbook_name}-{now_filename_stamp()}"

        out_dir = setup_run_dir(self.output_dir, self.playbook_name, run_id)
        run_logger = RunLogger(out_dir)
        evidence_dir = out_dir / "evidence" / self.playbook_name

        browser_adapter = BrowserAdapter(
            profile_dir=Path(config.browser.profile_dir) if config.browser.profile_dir else None,
            headless=config.browser.headless,
            timeout=config.browser.timeout_ms,
        )

        samples = self.load_samples()
        if not samples:
            write_results_csv(out_dir / "results.csv", [])
            run_logger.log("run_end", detail="no samples")
            return

        # Set common instance attrs for process_sample
        self._browser_adapter = browser_adapter
        self._evidence_dir = evidence_dir
        self._screenshot_mode = config.screenshot.mode

        # Let subclass create additional adapters
        self.create_adapters(config, browser_adapter)

        result_cols = self.result_columns
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
                result = existing_notes.get("result_data", {})
                if not result:
                    result = {col: "" for col in result_cols}
                    result["sample_id"] = sample_id
                    result["status"] = "success"
                    for col in result_cols:
                        if col in sample:
                            result[col] = sample[col]
                return result

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
                        # Persist result_data for resumability
                        notes = read_notes(sample_dir) or {}
                        notes["result_data"] = result
                        write_notes(sample_dir, notes)
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
                    result = {col: "" for col in result_cols}
                    result["sample_id"] = sample_id
                    result["status"] = "failed"
                    result["error"] = str(exc)
                    for col in result_cols:
                        if col in sample:
                            result[col] = sample[col]
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
        """Run the full playbook across all samples."""
        asyncio.run(self._run_async())

    def should_skip(self, sample: dict) -> bool:
        """Check if sample is already completed (for resumability)."""
        sample_id = generate_sample_id(
            primary_key=sample.get("primary_key"),
            url=sample.get("url"),
            name=sample.get("name"),
        )
        sample_dir = self.output_dir / "evidence" / self.playbook_name / sample_id
        notes = read_notes(sample_dir)
        return notes is not None and notes.get("status") == "success"
