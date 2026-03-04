"""Tests for GitHubChecksRunner with mocked adapters."""

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
from evidence_collector.runners.github_checks import GitHubChecksRunner, RESULT_COLUMNS


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("pr_url\nhttps://github.com/org/repo/pull/42\n")
    return csv_path


@pytest.fixture
def two_sample_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "pr_url\n"
        "https://github.com/org/repo/pull/42\n"
        "https://github.com/org/repo/pull/99\n"
    )
    return csv_path


@pytest.fixture
def mock_github_adapter() -> AsyncMock:
    adapter = AsyncMock()
    adapter.extract_pr_metadata = AsyncMock(
        return_value={
            "title": "Fix auth bug",
            "pr_or_commit_id": "42",
            "pr_creator": "alice",
            "approvers": ["bob", "carol"],
            "merger": "dave",
            "merge_status": "merged",
        }
    )
    adapter.extract_checks = AsyncMock(
        return_value={
            "check_summary": "passed=3; failed=0; pending=0; optional=0",
            "failed_checks": [],
            "merged_with_failures": False,
            "checks_raw": [],
        }
    )
    adapter.find_ticket_links = AsyncMock(return_value=[])
    adapter.get_ci_details_url = AsyncMock(return_value=None)
    return adapter


def _make_runner(
    input_path: Path, tmp_path: Path, config: RunConfig | None = None
) -> GitHubChecksRunner:
    out_dir = tmp_path / "output"
    return GitHubChecksRunner(
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
        s = samples[0]
        assert s["sample_id"] == "pr-42"
        assert s["github_url"] == "https://github.com/org/repo/pull/42"
        assert s["pr_or_commit"] == "pr"


class TestProcessSample:
    def test_success(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
        mock_page: AsyncMock,
    ):
        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "github-checks"
        evidence_dir.mkdir(parents=True)

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"
        runner._max_ci_details = 3

        sample = {
            "sample_id": "pr-42",
            "github_url": "https://github.com/org/repo/pull/42",
        }

        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "success"
        assert result["sample_id"] == "pr-42"
        assert result["title"] == "Fix auth bug"
        assert result["pr_creator"] == "alice"
        assert result["approvers"] == "bob;carol"
        assert result["merger"] == "dave"
        assert result["merge_status"] == "merged"

        # All keys present
        for col in RESULT_COLUMNS:
            assert col in result

        # Notes written with all 7 steps
        notes_path = evidence_dir / "pr-42" / "notes.json"
        assert notes_path.exists()
        notes = json.loads(notes_path.read_text())
        assert notes["status"] == "success"
        assert len(notes["steps_completed"]) == 7

        # Screenshots taken (pr_page + checks = 2 calls minimum)
        assert mock_browser.screenshot.call_count >= 2

    def test_auth_redirect(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
    ):
        mock_browser.open = AsyncMock(
            side_effect=LoginRedirectError("redirected to login")
        )

        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "github-checks"
        evidence_dir.mkdir(parents=True)

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"
        runner._max_ci_details = 3

        sample = {
            "sample_id": "pr-42",
            "github_url": "https://github.com/org/repo/pull/42",
        }

        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "failed"
        assert result["error"] == "AUTH_REQUIRED"

        notes_path = evidence_dir / "pr-42" / "notes.json"
        notes = json.loads(notes_path.read_text())
        assert notes["status"] == "failed"
        assert notes["steps_completed"] == []

    def test_page_not_found(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
    ):
        mock_browser.open = AsyncMock(
            side_effect=PageNotFoundError("404")
        )

        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "github-checks"
        evidence_dir.mkdir(parents=True)

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"
        runner._max_ci_details = 3

        sample = {
            "sample_id": "pr-42",
            "github_url": "https://github.com/org/repo/pull/42",
        }

        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "failed"
        assert result["error"] == "PAGE_NOT_FOUND"

    def test_jira_auth_partial(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
        mock_page: AsyncMock,
    ):
        """Jira auth failure results in partial status, not failed."""
        # GitHub opens fine, but Jira raises LoginRedirectError
        call_count = 0

        async def open_side_effect(url: str):
            nonlocal call_count
            call_count += 1
            if "jira" in url or "atlassian" in url:
                raise LoginRedirectError("jira login required")
            return mock_page

        mock_browser.open = AsyncMock(side_effect=open_side_effect)
        mock_github_adapter.find_ticket_links = AsyncMock(
            return_value=["https://jira.example.com/browse/PROJ-123"]
        )

        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "github-checks"
        evidence_dir.mkdir(parents=True)

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"
        runner._max_ci_details = 3

        sample = {
            "sample_id": "pr-42",
            "github_url": "https://github.com/org/repo/pull/42",
        }

        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "partial"
        assert "JIRA_AUTH_REQUIRED" in result.get("error", "")

        notes_path = evidence_dir / "pr-42" / "notes.json"
        notes = json.loads(notes_path.read_text())
        assert notes["status"] == "partial"
        assert len(notes["steps_completed"]) == 7
        assert "JIRA_AUTH_REQUIRED" in notes["errors"]

    def test_ci_details_screenshots(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
        mock_page: AsyncMock,
    ):
        """Failed checks trigger CI details screenshots."""
        ci_page = AsyncMock()
        ci_page.close = AsyncMock()
        ci_page.evaluate = AsyncMock(return_value=0)
        ci_page.wait_for_timeout = AsyncMock()

        open_calls = []

        async def open_side_effect(url: str):
            open_calls.append(url)
            if "ci-details" in url:
                return ci_page
            return mock_page

        mock_browser.open = AsyncMock(side_effect=open_side_effect)
        mock_github_adapter.extract_checks = AsyncMock(
            return_value={
                "check_summary": "passed=1; failed=1; pending=0; optional=0",
                "failed_checks": ["lint"],
                "merged_with_failures": True,
                "checks_raw": [],
            }
        )
        mock_github_adapter.get_ci_details_url = AsyncMock(
            return_value="https://github.com/ci-details/lint"
        )

        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "github-checks"
        evidence_dir.mkdir(parents=True)

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"
        runner._max_ci_details = 3

        sample = {
            "sample_id": "pr-42",
            "github_url": "https://github.com/org/repo/pull/42",
        }

        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "success"
        # CI details page opened
        assert any("ci-details" in u for u in open_calls)
        # CI page was closed
        ci_page.close.assert_called_once()


class TestRunAsync:
    def test_skips_completed_samples(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
    ):
        """Completed samples are skipped on re-run."""
        runner = _make_runner(sample_csv, tmp_path)
        out_dir = tmp_path / "output"

        # Pre-create notes.json with success status
        evidence_dir = out_dir / "evidence" / "github-checks"
        sample_dir = evidence_dir / "pr-42"
        sample_dir.mkdir(parents=True)
        (sample_dir / "screenshots").mkdir()
        (sample_dir / "downloads").mkdir()
        write_notes(sample_dir, {
            "sample_id": "pr-42",
            "status": "success",
            "steps_completed": ["open_primary_page"],
            "errors": [],
            "screenshots": [],
            "downloads": [],
        })

        # Patch BrowserAdapter and GitHubAdapter to avoid real browser
        with patch(
            "evidence_collector.runners.base.BrowserAdapter"
        ) as MockBA, patch(
            "evidence_collector.runners.github_checks.GitHubAdapter"
        ) as MockGA:
            MockBA.return_value = mock_browser
            MockGA.return_value = mock_github_adapter

            asyncio.run(runner._run_async())

        # process_sample should NOT have been called (open never called)
        mock_browser.open.assert_not_called()

        # results.csv should exist with the skipped sample
        results_csv = out_dir / "results.csv"
        assert results_csv.exists()

    def test_writes_results_csv(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
        mock_page: AsyncMock,
    ):
        """Run produces a results.csv with expected columns."""
        runner = _make_runner(sample_csv, tmp_path)
        out_dir = tmp_path / "output"

        with patch(
            "evidence_collector.runners.base.BrowserAdapter"
        ) as MockBA, patch(
            "evidence_collector.runners.github_checks.GitHubAdapter"
        ) as MockGA:
            MockBA.return_value = mock_browser
            MockGA.return_value = mock_github_adapter

            asyncio.run(runner._run_async())

        results_csv = out_dir / "results.csv"
        assert results_csv.exists()

        with open(results_csv) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["sample_id"] == "pr-42"
            assert rows[0]["status"] == "success"

    def test_writes_manifest(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
        mock_page: AsyncMock,
    ):
        """Run produces a valid run_manifest.json."""
        runner = _make_runner(sample_csv, tmp_path)
        out_dir = tmp_path / "output"

        with patch(
            "evidence_collector.runners.base.BrowserAdapter"
        ) as MockBA, patch(
            "evidence_collector.runners.github_checks.GitHubAdapter"
        ) as MockGA:
            MockBA.return_value = mock_browser
            MockGA.return_value = mock_github_adapter

            asyncio.run(runner._run_async())

        manifest_path = out_dir / "run_manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["playbook"] == "github-checks"
        assert manifest["started_at"]
        assert manifest["finished_at"]

    def test_empty_input(self, tmp_path: Path):
        """Empty CSV produces empty results.csv without error."""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("pr_url\n")

        runner = _make_runner(csv_path, tmp_path)
        out_dir = tmp_path / "output"

        with patch(
            "evidence_collector.runners.base.BrowserAdapter"
        ), patch(
            "evidence_collector.runners.github_checks.GitHubAdapter"
        ):
            asyncio.run(runner._run_async())

        results_csv = out_dir / "results.csv"
        assert results_csv.exists()
        assert results_csv.read_text() == ""
