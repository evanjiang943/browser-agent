"""Tests for TicketsRunner using the BaseRunner step engine."""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from evidence_collector.adapters.browser import LoginRedirectError, PageNotFoundError
from evidence_collector.config import RunConfig
from evidence_collector.io.paths import write_notes
from evidence_collector.runners.tickets import (
    RESULT_COLUMNS,
    TicketsRunner,
    load_ticket_samples,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("url\nhttps://jira.example.com/browse/PROJ-42\n")
    return csv_path


@pytest.fixture
def mock_page() -> AsyncMock:
    page = AsyncMock()
    # Title
    title_el = AsyncMock()
    title_el.inner_text = AsyncMock(return_value="Fix login bug")
    # Ticket ID
    ticket_id_el = AsyncMock()
    ticket_id_el.inner_text = AsyncMock(return_value="PROJ-42")
    # Assignee
    assignee_el = AsyncMock()
    assignee_el.inner_text = AsyncMock(return_value="alice")
    # Status
    status_el = AsyncMock()
    status_el.inner_text = AsyncMock(return_value="In Progress")
    # Due date
    due_el = AsyncMock()
    due_el.inner_text = AsyncMock(return_value="2026-04-01")

    def query_selector_side_effect(selector: str):
        if "title" in selector.lower():
            return title_el
        if "ticket-id" in selector or "issue-number" in selector:
            return ticket_id_el
        if "assignee" in selector:
            return assignee_el
        if "status" in selector:
            return status_el
        if "due" in selector:
            return due_el
        return None

    page.query_selector = AsyncMock(side_effect=query_selector_side_effect)
    page.close = AsyncMock()
    return page


def _make_runner(
    input_path: Path, tmp_path: Path, config: RunConfig | None = None
) -> TicketsRunner:
    out_dir = tmp_path / "output"
    return TicketsRunner(
        input_path=input_path,
        output_dir=out_dir,
        config=config or RunConfig(),
    )


# ── Tests ─────────────────────────────────────────────────────────────


class TestLoadSamples:
    def test_load_samples(self, sample_csv: Path, tmp_path: Path):
        runner = _make_runner(sample_csv, tmp_path)
        samples = runner.load_samples()
        assert len(samples) == 1
        assert samples[0]["url"] == "https://jira.example.com/browse/PROJ-42"
        assert "sample_id" in samples[0]

    def test_missing_url_column(self, tmp_path: Path):
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("name\nAlice\n")
        runner = _make_runner(csv_path, tmp_path)
        with pytest.raises(ValueError, match="Missing required columns"):
            runner.load_samples()

    def test_stable_ids(self, sample_csv: Path, tmp_path: Path):
        runner = _make_runner(sample_csv, tmp_path)
        a = runner.load_samples()
        b = runner.load_samples()
        assert a[0]["sample_id"] == b[0]["sample_id"]


class TestRunAsync:
    def test_success_flow(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_page: AsyncMock,
    ):
        runner = _make_runner(sample_csv, tmp_path)
        out_dir = tmp_path / "output"

        with patch(
            "evidence_collector.runners.tickets.BrowserAdapter"
        ) as MockBA:
            MockBA.return_value = mock_browser
            asyncio.run(runner._run_async())

        # Results CSV
        results_csv = out_dir / "results.csv"
        assert results_csv.exists()
        with open(results_csv) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["status"] == "success"
            assert rows[0]["title"] == "Fix login bug"
            assert rows[0]["assignee"] == "alice"

        # Manifest
        manifest_path = out_dir / "run_manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["playbook"] == "tickets"
        assert manifest["started_at"]
        assert manifest["finished_at"]

    def test_auth_failure(
        self,
        sample_csv: Path,
        tmp_path: Path,
    ):
        mock_browser = AsyncMock()
        mock_browser.open = AsyncMock(
            side_effect=LoginRedirectError("login redirect")
        )
        mock_browser.screenshot = AsyncMock()
        mock_browser.close = AsyncMock()

        runner = _make_runner(sample_csv, tmp_path)
        out_dir = tmp_path / "output"

        with patch(
            "evidence_collector.runners.tickets.BrowserAdapter"
        ) as MockBA:
            MockBA.return_value = mock_browser
            asyncio.run(runner._run_async())

        results_csv = out_dir / "results.csv"
        with open(results_csv) as f:
            rows = list(csv.DictReader(f))
            assert rows[0]["status"] == "failed"
            assert rows[0]["error"] == "AUTH_REQUIRED"

    def test_page_not_found(
        self,
        sample_csv: Path,
        tmp_path: Path,
    ):
        mock_browser = AsyncMock()
        mock_browser.open = AsyncMock(
            side_effect=PageNotFoundError("404")
        )
        mock_browser.screenshot = AsyncMock()
        mock_browser.close = AsyncMock()

        runner = _make_runner(sample_csv, tmp_path)
        out_dir = tmp_path / "output"

        with patch(
            "evidence_collector.runners.tickets.BrowserAdapter"
        ) as MockBA:
            MockBA.return_value = mock_browser
            asyncio.run(runner._run_async())

        results_csv = out_dir / "results.csv"
        with open(results_csv) as f:
            rows = list(csv.DictReader(f))
            assert rows[0]["status"] == "failed"
            assert rows[0]["error"] == "PAGE_NOT_FOUND"

    def test_empty_input(self, tmp_path: Path):
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("url\n")

        runner = _make_runner(csv_path, tmp_path)
        out_dir = tmp_path / "output"

        with patch("evidence_collector.runners.tickets.BrowserAdapter"):
            asyncio.run(runner._run_async())

        results_csv = out_dir / "results.csv"
        assert results_csv.exists()
        assert results_csv.read_text() == ""

    def test_skips_completed_samples(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
    ):
        runner = _make_runner(sample_csv, tmp_path)
        out_dir = tmp_path / "output"

        samples = runner.load_samples()
        sample_id = samples[0]["sample_id"]

        # Pre-create completed notes
        evidence_dir = out_dir / "evidence" / "tickets"
        sample_dir = evidence_dir / sample_id
        sample_dir.mkdir(parents=True)
        (sample_dir / "screenshots").mkdir()
        (sample_dir / "downloads").mkdir()
        write_notes(sample_dir, {
            "sample_id": sample_id,
            "status": "success",
            "steps_completed": ["open_ticket", "screenshot_ticket", "extract_fields", "close_page"],
            "errors": [],
            "screenshots": [],
            "downloads": [],
        })

        with patch(
            "evidence_collector.runners.tickets.BrowserAdapter"
        ) as MockBA:
            MockBA.return_value = mock_browser
            asyncio.run(runner._run_async())

        # Browser.open should NOT have been called
        mock_browser.open.assert_not_called()

        results_csv = out_dir / "results.csv"
        assert results_csv.exists()
