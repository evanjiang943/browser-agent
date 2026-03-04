"""Tests for CodeRecencyRunner with mocked adapters."""

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
from evidence_collector.runners.code_recency import CodeRecencyRunner, RESULT_COLUMNS


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "repo_url,code_string,time_window_days\n"
        "https://github.com/org/repo,def hello(),365\n"
    )
    return csv_path


@pytest.fixture
def two_sample_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "repo_url,code_string,time_window_days\n"
        "https://github.com/org/repo,def hello(),365\n"
        "https://github.com/org/repo,class Foo,180\n"
    )
    return csv_path


@pytest.fixture
def mock_page() -> AsyncMock:
    page = AsyncMock()
    page.query_selector.return_value = None
    page.query_selector_all.return_value = []
    page.close = AsyncMock()
    page.inner_text = AsyncMock(return_value="")
    page.evaluate = AsyncMock(return_value=0)
    page.wait_for_timeout = AsyncMock()
    return page


@pytest.fixture
def mock_browser(mock_page: AsyncMock) -> AsyncMock:
    browser = AsyncMock()
    browser.open = AsyncMock(return_value=mock_page)
    browser.screenshot = AsyncMock()
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def mock_github_adapter() -> AsyncMock:
    adapter = AsyncMock()
    adapter.search_code = AsyncMock(
        return_value=(
            "https://github.com/org/repo/blob/main/src/hello.py#L10-L15",
            (10, 15),
        )
    )
    adapter.open_blame_view = AsyncMock()
    adapter.extract_blame_dates = AsyncMock(
        return_value=[
            {"line": 10, "date": "2025-06-15T10:00:00Z", "sha": "abc123def456"},
            {"line": 11, "date": "2025-06-14T10:00:00Z", "sha": "abc123def456"},
            {"line": 12, "date": "2025-01-01T10:00:00Z", "sha": "oldsha123456"},
        ]
    )
    adapter.extract_commit_diff_summary = AsyncMock(
        return_value={
            "files_changed": 3,
            "lines_added": 25,
            "lines_removed": 10,
            "diff_text_snippet": "+def hello():\n+    print('hi')",
        }
    )
    return adapter


def _make_runner(
    input_path: Path, tmp_path: Path, config: RunConfig | None = None
) -> CodeRecencyRunner:
    out_dir = tmp_path / "output"
    return CodeRecencyRunner(
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
        assert s["repo_url"] == "https://github.com/org/repo"
        assert s["code_string"] == "def hello()"
        assert s["time_window_days"] == 365
        assert "sample_id" in s

    def test_load_samples_stable_ids(self, sample_csv: Path, tmp_path: Path):
        runner = _make_runner(sample_csv, tmp_path)
        first = runner.load_samples()
        second = runner.load_samples()
        assert first[0]["sample_id"] == second[0]["sample_id"]

    def test_load_samples_missing_columns(self, tmp_path: Path):
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("name,age\nAlice,30\n")
        runner = _make_runner(csv_path, tmp_path)
        with pytest.raises(ValueError, match="Missing required columns"):
            runner.load_samples()


class TestProcessSample:
    def test_success_within_window(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
        mock_page: AsyncMock,
    ):
        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "code-recency"
        evidence_dir.mkdir(parents=True)

        # Return different pages for different open() calls
        blame_page = AsyncMock()
        blame_page.close = AsyncMock()
        commit_page = AsyncMock()
        commit_page.close = AsyncMock()

        mock_github_adapter.open_blame_view = AsyncMock(return_value=blame_page)

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"

        sample = runner.load_samples()[0]
        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "success"
        assert result["sample_id"] == sample["sample_id"]
        assert result["last_change_date"] == "2025-06-15T10:00:00Z"
        assert result["commit_sha"] == "abc123def456"
        assert result["within_window"] == "True"
        assert result["material_change_flag"] == "True"
        assert "3 files" in result["rationale"]

        # All keys present
        for col in RESULT_COLUMNS:
            assert col in result

        # Notes written
        notes_path = evidence_dir / sample["sample_id"] / "notes.json"
        assert notes_path.exists()
        notes = json.loads(notes_path.read_text())
        assert notes["status"] == "success"
        assert "search_code" in notes["steps_completed"]
        assert "extract_blame_dates" in notes["steps_completed"]
        assert "materiality_assessment" in notes["steps_completed"]

    def test_success_outside_window(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
        mock_page: AsyncMock,
    ):
        """Old blame dates result in within_window=False, material=False."""
        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "code-recency"
        evidence_dir.mkdir(parents=True)

        blame_page = AsyncMock()
        blame_page.close = AsyncMock()
        mock_github_adapter.open_blame_view = AsyncMock(return_value=blame_page)

        # All blame dates are old
        mock_github_adapter.extract_blame_dates = AsyncMock(
            return_value=[
                {"line": 10, "date": "2020-01-01T00:00:00Z", "sha": "oldsha000000"},
            ]
        )

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"

        sample = runner.load_samples()[0]
        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "success"
        assert result["within_window"] == "False"
        assert result["material_change_flag"] == "False"
        assert "stable" in result["rationale"].lower()

    def test_code_not_found(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
    ):
        mock_github_adapter.search_code = AsyncMock(return_value=None)

        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "code-recency"
        evidence_dir.mkdir(parents=True)

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"

        sample = runner.load_samples()[0]
        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "failed"
        assert result["error"] == "CODE_NOT_FOUND"

    def test_auth_redirect(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
    ):
        mock_github_adapter.search_code = AsyncMock(
            side_effect=LoginRedirectError("login required")
        )

        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "code-recency"
        evidence_dir.mkdir(parents=True)

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"

        sample = runner.load_samples()[0]
        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "failed"
        assert result["error"] == "AUTH_REQUIRED"

    def test_no_blame_data_partial(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
        mock_page: AsyncMock,
    ):
        """Empty blame data results in partial status."""
        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "code-recency"
        evidence_dir.mkdir(parents=True)

        blame_page = AsyncMock()
        blame_page.close = AsyncMock()
        mock_github_adapter.open_blame_view = AsyncMock(return_value=blame_page)
        mock_github_adapter.extract_blame_dates = AsyncMock(return_value=[])

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"

        sample = runner.load_samples()[0]
        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "partial"
        assert "NO_BLAME_DATA" in result["error"]

    def test_trivial_change_not_material(
        self,
        sample_csv: Path,
        tmp_path: Path,
        mock_browser: AsyncMock,
        mock_github_adapter: AsyncMock,
        mock_page: AsyncMock,
    ):
        """Small diff within window should flag as not material."""
        runner = _make_runner(sample_csv, tmp_path)
        evidence_dir = tmp_path / "output" / "evidence" / "code-recency"
        evidence_dir.mkdir(parents=True)

        blame_page = AsyncMock()
        blame_page.close = AsyncMock()
        mock_github_adapter.open_blame_view = AsyncMock(return_value=blame_page)
        mock_github_adapter.extract_commit_diff_summary = AsyncMock(
            return_value={
                "files_changed": 1,
                "lines_added": 2,
                "lines_removed": 1,
                "diff_text_snippet": "- old\n+ new",
            }
        )

        runner._browser_adapter = mock_browser
        runner._github_adapter = mock_github_adapter
        runner._evidence_dir = evidence_dir
        runner._screenshot_mode = "viewport"

        sample = runner.load_samples()[0]
        result = asyncio.run(runner.process_sample(sample))

        assert result["status"] == "success"
        assert result["within_window"] == "True"
        assert result["material_change_flag"] == "False"
        assert "trivial" in result["rationale"].lower()


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

        samples = runner.load_samples()
        sample_id = samples[0]["sample_id"]

        # Pre-create notes.json with success status
        evidence_dir = out_dir / "evidence" / "code-recency"
        sample_dir = evidence_dir / sample_id
        sample_dir.mkdir(parents=True)
        (sample_dir / "screenshots").mkdir()
        (sample_dir / "downloads").mkdir()
        write_notes(sample_dir, {
            "sample_id": sample_id,
            "status": "success",
            "steps_completed": ["search_code"],
            "errors": [],
            "screenshots": [],
            "downloads": [],
        })

        with patch(
            "evidence_collector.runners.code_recency.BrowserAdapter"
        ) as MockBA, patch(
            "evidence_collector.runners.code_recency.GitHubAdapter"
        ) as MockGA:
            MockBA.return_value = mock_browser
            MockGA.return_value = mock_github_adapter

            asyncio.run(runner._run_async())

        # process_sample should NOT have been called
        mock_browser.open.assert_not_called()

        # results.csv should exist
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

        blame_page = AsyncMock()
        blame_page.close = AsyncMock()
        mock_github_adapter.open_blame_view = AsyncMock(return_value=blame_page)

        with patch(
            "evidence_collector.runners.code_recency.BrowserAdapter"
        ) as MockBA, patch(
            "evidence_collector.runners.code_recency.GitHubAdapter"
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

        blame_page = AsyncMock()
        blame_page.close = AsyncMock()
        mock_github_adapter.open_blame_view = AsyncMock(return_value=blame_page)

        with patch(
            "evidence_collector.runners.code_recency.BrowserAdapter"
        ) as MockBA, patch(
            "evidence_collector.runners.code_recency.GitHubAdapter"
        ) as MockGA:
            MockBA.return_value = mock_browser
            MockGA.return_value = mock_github_adapter

            asyncio.run(runner._run_async())

        manifest_path = out_dir / "run_manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["playbook"] == "code-recency"
        assert manifest["started_at"]
        assert manifest["finished_at"]

    def test_empty_input(self, tmp_path: Path):
        """Empty CSV produces empty results.csv without error."""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("repo_url,code_string\n")

        runner = _make_runner(csv_path, tmp_path)
        out_dir = tmp_path / "output"

        with patch(
            "evidence_collector.runners.code_recency.BrowserAdapter"
        ), patch(
            "evidence_collector.runners.code_recency.GitHubAdapter"
        ):
            asyncio.run(runner._run_async())

        results_csv = out_dir / "results.csv"
        assert results_csv.exists()
        assert results_csv.read_text() == ""


class TestLoadCodeRecencySamples:
    """Tests for load_code_recency_samples via the runner."""

    def test_default_window(self, tmp_path: Path):
        csv_path = tmp_path / "no_window.csv"
        csv_path.write_text("repo_url,code_string\nhttps://github.com/a/b,foo\n")
        runner = _make_runner(csv_path, tmp_path)
        samples = runner.load_samples()
        assert samples[0]["time_window_days"] == 365

    def test_custom_window(self, tmp_path: Path):
        csv_path = tmp_path / "custom.csv"
        csv_path.write_text(
            "repo_url,code_string,time_window_days\n"
            "https://github.com/a/b,foo,90\n"
        )
        runner = _make_runner(csv_path, tmp_path)
        samples = runner.load_samples()
        assert samples[0]["time_window_days"] == 90

    def test_since_date(self, tmp_path: Path):
        csv_path = tmp_path / "since.csv"
        csv_path.write_text(
            "repo_url,code_string,since_date\n"
            "https://github.com/a/b,foo,2025-01-01\n"
        )
        runner = _make_runner(csv_path, tmp_path)
        samples = runner.load_samples()
        # Should compute days from 2025-01-01 to now (> 365 days in 2026)
        assert samples[0]["time_window_days"] > 0
