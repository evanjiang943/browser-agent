"""Ticket screenshots + field extraction playbook runner.

Uses the generic BaseRunner step engine — this module only defines
the step functions, input/output schemas, and orchestration wiring.
"""

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
from evidence_collector.config import RunConfig
from evidence_collector.evidence.logging import RunLogger
from evidence_collector.evidence.manifest import RunManifest, write_manifest
from evidence_collector.io.csv_utils import write_results_csv
from evidence_collector.io.paths import setup_run_dir
from evidence_collector.io.spreadsheets import read_input, validate_columns
from evidence_collector.utils.time import now_filename_stamp, now_iso

from .base import BaseRunner, SampleContext, StepDefinition

logger = logging.getLogger(__name__)

# ── Schemas ──────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = ["url"]

RESULT_COLUMNS = [
    "sample_id",
    "url",
    "ticket_id",
    "title",
    "assignee",
    "status_field",
    "due_date",
    "status",
    "error",
]


# ── Step functions ───────────────────────────────────────────────────────


async def open_ticket(ctx: SampleContext) -> None:
    """Navigate to the ticket URL."""
    url = ctx.input["url"]
    try:
        page = await ctx.browser.open(url)
    except LoginRedirectError:
        ctx.fail("AUTH_REQUIRED")
    except PageNotFoundError:
        ctx.fail("PAGE_NOT_FOUND")
    ctx.state["_page"] = page
    ctx.record(url=url)


async def screenshot_ticket(ctx: SampleContext) -> None:
    """Take a screenshot of the ticket page."""
    page = ctx.state["_page"]
    await ctx.screenshot(page, "ticket_page", system="ticket")


async def extract_fields(ctx: SampleContext) -> None:
    """Extract ticket metadata from the page DOM."""
    page = ctx.state["_page"]

    # Title
    title_el = await page.query_selector(
        "h1, [data-testid='title'], .issue-title, .ticket-title"
    )
    title = (await title_el.inner_text()).strip() if title_el else ""

    # Ticket ID — look for a #NNN or KEY-NNN pattern in the heading area
    ticket_id_el = await page.query_selector(
        "[data-testid='ticket-id'], .ticket-id, .issue-number"
    )
    ticket_id = (await ticket_id_el.inner_text()).strip() if ticket_id_el else ""

    # Assignee
    assignee_el = await page.query_selector(
        "[data-testid='assignee'], .assignee, [data-field='assignee']"
    )
    assignee = (await assignee_el.inner_text()).strip() if assignee_el else ""

    # Status
    status_el = await page.query_selector(
        "[data-testid='status'], .status-badge, [data-field='status']"
    )
    status_field = (await status_el.inner_text()).strip() if status_el else ""

    # Due date
    due_el = await page.query_selector(
        "[data-testid='due-date'], .due-date, [data-field='due_date']"
    )
    due_date = (await due_el.inner_text()).strip() if due_el else ""

    ctx.record(
        ticket_id=ticket_id,
        title=title,
        assignee=assignee,
        status_field=status_field,
        due_date=due_date,
    )


async def close_page(ctx: SampleContext) -> None:
    """Close the ticket page."""
    page = ctx.state.pop("_page", None)
    if page is not None:
        await page.close()


STEPS = [
    StepDefinition(name="open_ticket", fn=open_ticket),
    StepDefinition(name="screenshot_ticket", fn=screenshot_ticket),
    StepDefinition(name="extract_fields", fn=extract_fields),
    StepDefinition(name="close_page", fn=close_page, required=False),
]


# ── Loader ───────────────────────────────────────────────────────────────


def load_ticket_samples(input_path: Path) -> list[dict]:
    """Read and validate the ticket input CSV/XLSX."""
    rows = read_input(input_path)
    if not rows:
        return []
    missing = validate_columns(rows, REQUIRED_COLUMNS)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    from evidence_collector.evidence.naming import generate_sample_id

    samples = []
    for row in rows:
        url = str(row["url"]).strip()
        if not url:
            continue
        sample_id = generate_sample_id(url=url)
        samples.append({"sample_id": sample_id, "url": url, **row})
    return samples


# ── Public runner class ──────────────────────────────────────────────────


class TicketsRunner:
    """Playbook A: open ticket URLs, screenshot, extract fields.

    Thin orchestration shell — all step logic lives in module-level
    async functions wired through :class:`BaseRunner`.
    """

    def __init__(self, input_path: Path, output_dir: Path, config: Any) -> None:
        self.input_path = input_path
        self.output_dir = output_dir
        self.config = config if isinstance(config, RunConfig) else RunConfig()

    @property
    def playbook_name(self) -> str:
        return "tickets"

    def load_samples(self) -> list[dict]:
        return load_ticket_samples(self.input_path)

    async def _run_async(self) -> None:
        config = self.config
        started_at = now_iso()
        run_id = f"tickets-{now_filename_stamp()}"

        out_dir = setup_run_dir(self.output_dir, self.playbook_name, run_id)
        run_logger = RunLogger(out_dir)
        evidence_dir = out_dir / "evidence" / self.playbook_name

        browser = BrowserAdapter(
            profile_dir=(
                Path(config.browser.profile_dir)
                if config.browser.profile_dir
                else None
            ),
            headless=config.browser.headless,
            timeout=config.browser.timeout_ms,
        )

        samples = self.load_samples()

        runner = BaseRunner(
            steps=STEPS,
            result_schema=RESULT_COLUMNS,
            browser=browser,
            logger=run_logger,
            evidence_dir=evidence_dir,
            config=config,
        )

        if not samples:
            write_results_csv(out_dir / "results.csv", [])
            run_logger.log("run_end", detail="no samples")
        else:
            try:
                results = await runner.run_all(
                    samples,
                    concurrency=config.concurrency,
                    max_pages_per_minute=config.throttle.max_pages_per_minute,
                    retry_attempts=config.throttle.retry_attempts,
                    backoff_base=config.throttle.backoff_base_seconds,
                )
            finally:
                await browser.close()

            write_results_csv(out_dir / "results.csv", results)
            run_logger.log("run_end", detail="complete")

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

    def run(self) -> None:
        asyncio.run(self._run_async())
