"""Tests for the generic BaseRunner step engine and SampleContext."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from evidence_collector.runners.base import (
    BaseRunner,
    SampleContext,
    StepDefinition,
    StepFailed,
    SubItemContext,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_runner(
    steps: list[StepDefinition],
    result_schema: list[str],
    tmp_path: Path,
    browser: AsyncMock | None = None,
) -> BaseRunner:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    logger = AsyncMock()
    logger.log = lambda *a, **kw: None  # no-op logger
    return BaseRunner(
        steps=steps,
        result_schema=result_schema,
        browser=browser or AsyncMock(),
        logger=logger,
        evidence_dir=evidence_dir,
    )


SCHEMA = ["sample_id", "url", "title", "status", "error"]


# ── StepFailed ───────────────────────────────────────────────────────────


class TestStepFailed:
    def test_attributes(self):
        e = StepFailed("AUTH_REQUIRED", "redirected to login")
        assert e.error_code == "AUTH_REQUIRED"
        assert e.message == "redirected to login"
        assert "AUTH_REQUIRED" in str(e)

    def test_no_message(self):
        e = StepFailed("NOT_FOUND")
        assert str(e) == "NOT_FOUND"


# ── SampleContext ────────────────────────────────────────────────────────


class TestSampleContext:
    def test_record_merges_state(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        ctx = SampleContext(
            sample_id="s1",
            input={"url": "http://example.com"},
            evidence_dir=evidence_dir,
            browser=AsyncMock(),
            logger=AsyncMock(),
        )
        ctx.record(title="Hello", assignee="alice")
        ctx.record(title="Updated")
        assert ctx.state == {"title": "Updated", "assignee": "alice"}

    def test_fail_raises_step_failed(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        ctx = SampleContext(
            sample_id="s1",
            input={},
            evidence_dir=evidence_dir,
            browser=AsyncMock(),
            logger=AsyncMock(),
        )
        with pytest.raises(StepFailed, match="AUTH_REQUIRED"):
            ctx.fail("AUTH_REQUIRED", "login redirect")

    def test_save_file(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        ctx = SampleContext(
            sample_id="s1",
            input={},
            evidence_dir=evidence_dir,
            browser=AsyncMock(),
            logger=AsyncMock(),
        )
        path = asyncio.run(ctx.save_file(b"hello", "data.txt"))
        assert path.exists()
        assert path.read_bytes() == b"hello"
        assert "data.txt" in ctx._notes.downloads

    def test_screenshot(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        browser = AsyncMock()
        browser.screenshot = AsyncMock()
        ctx = SampleContext(
            sample_id="s1",
            input={},
            evidence_dir=evidence_dir,
            browser=browser,
            logger=AsyncMock(),
        )
        page = AsyncMock()
        paths = asyncio.run(ctx.screenshot(page, "ticket_page", system="jira"))
        assert len(paths) == 1
        browser.screenshot.assert_called_once()
        assert len(ctx._notes.screenshots) == 1


# ── BaseRunner.run_sample ────────────────────────────────────────────────


class TestRunSample:
    def test_all_steps_success(self, tmp_path):
        async def step_a(ctx: SampleContext) -> None:
            ctx.record(title="Hello")

        async def step_b(ctx: SampleContext) -> None:
            ctx.record(url="http://example.com")

        steps = [
            StepDefinition(name="step_a", fn=step_a),
            StepDefinition(name="step_b", fn=step_b),
        ]
        runner = _make_runner(steps, SCHEMA, tmp_path)
        sample = {"sample_id": "s1"}

        result = asyncio.run(runner.run_sample(sample))

        assert result["status"] == "success"
        assert result["title"] == "Hello"
        assert result["url"] == "http://example.com"
        assert result["sample_id"] == "s1"

        # Notes persisted
        notes_path = tmp_path / "evidence" / "s1" / "notes.json"
        assert notes_path.exists()
        notes = json.loads(notes_path.read_text())
        assert notes["status"] == "success"
        assert notes["steps_completed"] == ["step_a", "step_b"]

    def test_required_step_failure_aborts(self, tmp_path):
        async def step_a(ctx: SampleContext) -> None:
            ctx.fail("AUTH_REQUIRED")

        async def step_b(ctx: SampleContext) -> None:
            ctx.record(title="never reached")

        steps = [
            StepDefinition(name="step_a", fn=step_a),
            StepDefinition(name="step_b", fn=step_b),
        ]
        runner = _make_runner(steps, SCHEMA, tmp_path)
        result = asyncio.run(runner.run_sample({"sample_id": "s1"}))

        assert result["status"] == "failed"
        assert result["error"] == "AUTH_REQUIRED"
        assert result.get("title") == ""

        notes = json.loads(
            (tmp_path / "evidence" / "s1" / "notes.json").read_text()
        )
        assert notes["status"] == "failed"
        assert "step_b" not in notes["steps_completed"]

    def test_optional_step_failure_marks_partial(self, tmp_path):
        async def step_a(ctx: SampleContext) -> None:
            ctx.record(title="Hello")

        async def step_b(ctx: SampleContext) -> None:
            ctx.fail("OPTIONAL_FAIL")

        async def step_c(ctx: SampleContext) -> None:
            ctx.record(url="http://example.com")

        steps = [
            StepDefinition(name="step_a", fn=step_a),
            StepDefinition(name="step_b", fn=step_b, required=False),
            StepDefinition(name="step_c", fn=step_c),
        ]
        runner = _make_runner(steps, SCHEMA, tmp_path)
        result = asyncio.run(runner.run_sample({"sample_id": "s1"}))

        assert result["status"] == "partial"
        assert "OPTIONAL_FAIL" in result["error"]
        assert result["title"] == "Hello"
        assert result["url"] == "http://example.com"

        notes = json.loads(
            (tmp_path / "evidence" / "s1" / "notes.json").read_text()
        )
        assert notes["status"] == "partial"
        # All steps recorded (optional failure still counts as completed)
        assert notes["steps_completed"] == ["step_a", "step_b", "step_c"]

    def test_unexpected_exception_in_required_step(self, tmp_path):
        async def step_boom(ctx: SampleContext) -> None:
            raise RuntimeError("unexpected")

        steps = [StepDefinition(name="step_boom", fn=step_boom)]
        runner = _make_runner(steps, SCHEMA, tmp_path)
        result = asyncio.run(runner.run_sample({"sample_id": "s1"}))

        assert result["status"] == "failed"
        assert "unexpected" in result["error"]

    def test_result_schema_fills_missing_with_empty(self, tmp_path):
        async def step(ctx: SampleContext) -> None:
            ctx.record(title="Only title set")

        steps = [StepDefinition(name="step", fn=step)]
        runner = _make_runner(steps, SCHEMA, tmp_path)
        result = asyncio.run(runner.run_sample({"sample_id": "s1"}))

        for col in SCHEMA:
            assert col in result
        assert result["url"] == ""

    def test_resumability_skips_completed_steps(self, tmp_path):
        """If notes.json exists with completed steps, those steps are skipped."""
        call_log = []

        async def step_a(ctx: SampleContext) -> None:
            call_log.append("a")
            ctx.record(title="Hello")

        async def step_b(ctx: SampleContext) -> None:
            call_log.append("b")
            ctx.record(url="http://example.com")

        steps = [
            StepDefinition(name="step_a", fn=step_a),
            StepDefinition(name="step_b", fn=step_b),
        ]
        runner = _make_runner(steps, SCHEMA, tmp_path)

        # Pre-create notes with step_a already completed
        sample_dir = tmp_path / "evidence" / "s1"
        sample_dir.mkdir(parents=True)
        (sample_dir / "screenshots").mkdir()
        (sample_dir / "downloads").mkdir()
        (sample_dir / "notes.json").write_text(
            json.dumps({
                "sample_id": "s1",
                "status": "pending",
                "steps_completed": ["step_a"],
                "errors": [],
                "screenshots": [],
                "downloads": [],
            })
        )

        result = asyncio.run(runner.run_sample({"sample_id": "s1"}))

        # Only step_b was actually called
        assert call_log == ["b"]
        assert result["status"] == "success"

    def test_resumability_skips_fully_completed(self, tmp_path):
        """Samples with status=success are returned immediately."""
        call_log = []

        async def step_a(ctx: SampleContext) -> None:
            call_log.append("a")

        steps = [StepDefinition(name="step_a", fn=step_a)]
        runner = _make_runner(steps, SCHEMA, tmp_path)

        sample_dir = tmp_path / "evidence" / "s1"
        sample_dir.mkdir(parents=True)
        (sample_dir / "screenshots").mkdir()
        (sample_dir / "downloads").mkdir()
        (sample_dir / "notes.json").write_text(
            json.dumps({
                "sample_id": "s1",
                "status": "success",
                "steps_completed": ["step_a"],
                "errors": [],
                "screenshots": [],
                "downloads": [],
            })
        )

        result = asyncio.run(runner.run_sample({"sample_id": "s1"}))
        assert result["status"] == "success"
        assert call_log == []  # No steps executed


# ── BaseRunner.run_all ───────────────────────────────────────────────────


class TestRunAll:
    def test_processes_multiple_samples(self, tmp_path):
        async def step(ctx: SampleContext) -> None:
            ctx.record(title=f"title-{ctx.sample_id}")

        steps = [StepDefinition(name="step", fn=step)]
        runner = _make_runner(steps, SCHEMA, tmp_path)

        samples = [{"sample_id": "s1"}, {"sample_id": "s2"}, {"sample_id": "s3"}]
        results = asyncio.run(runner.run_all(samples, concurrency=2))

        assert len(results) == 3
        ids = {r["sample_id"] for r in results}
        assert ids == {"s1", "s2", "s3"}
        assert all(r["status"] == "success" for r in results)

    def test_empty_samples(self, tmp_path):
        steps = [StepDefinition(name="noop", fn=AsyncMock())]
        runner = _make_runner(steps, SCHEMA, tmp_path)
        results = asyncio.run(runner.run_all([]))
        assert results == []

    def test_skips_completed_in_run_all(self, tmp_path):
        call_log = []

        async def step(ctx: SampleContext) -> None:
            call_log.append(ctx.sample_id)

        steps = [StepDefinition(name="step", fn=step)]
        runner = _make_runner(steps, SCHEMA, tmp_path)

        # Pre-complete s1
        sample_dir = tmp_path / "evidence" / "s1"
        sample_dir.mkdir(parents=True)
        (sample_dir / "screenshots").mkdir()
        (sample_dir / "downloads").mkdir()
        (sample_dir / "notes.json").write_text(
            json.dumps({
                "sample_id": "s1",
                "status": "success",
                "steps_completed": ["step"],
                "errors": [],
                "screenshots": [],
                "downloads": [],
            })
        )

        samples = [{"sample_id": "s1"}, {"sample_id": "s2"}]
        results = asyncio.run(runner.run_all(samples))

        assert len(results) == 2
        # s1 was skipped, s2 was processed
        assert "s1" not in call_log
        assert "s2" in call_log
        assert results[0]["status"] == "success"
        assert results[1]["status"] == "success"


# ── SubItemContext ───────────────────────────────────────────────────────


def _make_ctx(tmp_path: Path, sample_id: str = "s1") -> SampleContext:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return SampleContext(
        sample_id=sample_id,
        input={},
        evidence_dir=evidence_dir,
        browser=AsyncMock(),
        logger=AsyncMock(),
    )


class TestSubItemCreation:
    def test_creates_sub_item(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        sub = ctx.sub_item("cite-1")

        assert isinstance(sub, SubItemContext)
        assert sub.sub_id == "cite-1"
        assert sub.parent is ctx
        assert sub.evidence_dir.exists()
        assert (sub.evidence_dir / "screenshots").exists()

    def test_sub_item_evidence_dir_path(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        sub = ctx.sub_item("cite-42")
        expected = ctx.sample_dir / "sub_items" / "cite-42"
        assert sub.evidence_dir == expected

    def test_sub_item_idempotent(self, tmp_path):
        """Calling sub_item() twice with the same id returns contexts sharing state."""
        ctx = _make_ctx(tmp_path)
        sub1 = ctx.sub_item("cite-1")
        sub1.record(url="http://a.com")
        sub2 = ctx.sub_item("cite-1")
        assert sub2.state["url"] == "http://a.com"

    def test_multiple_sub_items(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.sub_item("a")
        ctx.sub_item("b")
        ctx.sub_item("c")
        assert set(ctx._notes.sub_items.keys()) == {"a", "b", "c"}


class TestSubItemRecord:
    def test_record_updates_state(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        sub = ctx.sub_item("cite-1")
        sub.record(url="http://example.com", alive=True)
        assert sub.state == {"url": "http://example.com", "alive": True}

    def test_record_merges(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        sub = ctx.sub_item("cite-1")
        sub.record(url="http://example.com")
        sub.record(status_code=200)
        assert sub.state == {"url": "http://example.com", "status_code": 200}


class TestSubItemStatus:
    def test_mark_success(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        sub = ctx.sub_item("cite-1")
        sub.mark_success()
        assert ctx._notes.sub_items["cite-1"].status == "success"

    def test_mark_failed(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        sub = ctx.sub_item("cite-1")
        sub.mark_failed("TIMEOUT")
        assert ctx._notes.sub_items["cite-1"].status == "failed"
        assert "TIMEOUT" in ctx._notes.sub_items["cite-1"].errors

    def test_fail_raises_and_marks(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        sub = ctx.sub_item("cite-1")
        with pytest.raises(StepFailed, match="DEAD_LINK"):
            sub.fail("DEAD_LINK")
        assert ctx._notes.sub_items["cite-1"].status == "failed"
        assert "DEAD_LINK" in ctx._notes.sub_items["cite-1"].errors


class TestSubItemScreenshot:
    def test_screenshot_saves_to_sub_dir(self, tmp_path):
        browser = AsyncMock()
        browser.screenshot = AsyncMock()
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        ctx = SampleContext(
            sample_id="s1",
            input={},
            evidence_dir=evidence_dir,
            browser=browser,
            logger=AsyncMock(),
        )
        sub = ctx.sub_item("cite-1")
        page = AsyncMock()
        paths = asyncio.run(sub.screenshot(page, "verify", system="web"))

        assert len(paths) == 1
        # Screenshot path is under the sub-item's evidence dir
        assert "sub_items" in str(paths[0])
        assert "cite-1" in str(paths[0])
        browser.screenshot.assert_called_once()
        assert len(sub._sub_notes.screenshots) == 1


class TestCompletedSubItems:
    def test_empty(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        assert ctx.completed_sub_items() == set()

    def test_mixed_statuses(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        s1 = ctx.sub_item("a")
        s1.mark_success()
        s2 = ctx.sub_item("b")
        s2.mark_failed("ERR")
        s3 = ctx.sub_item("c")
        s3.mark_success()
        ctx.sub_item("d")  # pending

        assert ctx.completed_sub_items() == {"a", "c"}

    def test_used_for_skip_logic(self, tmp_path):
        """Demonstrates the skip pattern in a step function."""
        ctx = _make_ctx(tmp_path)
        sub = ctx.sub_item("a")
        sub.mark_success()

        processed = []
        for sid in ["a", "b", "c"]:
            if sid in ctx.completed_sub_items():
                continue
            processed.append(sid)
            s = ctx.sub_item(sid)
            s.mark_success()

        assert processed == ["b", "c"]
        assert ctx.completed_sub_items() == {"a", "b", "c"}


class TestAllSubItemStates:
    def test_empty(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        assert ctx.all_sub_item_states() == []

    def test_collects_states(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        s1 = ctx.sub_item("a")
        s1.record(url="http://a.com", alive=True)
        s1.mark_success()
        s2 = ctx.sub_item("b")
        s2.record(url="http://b.com", alive=False)
        s2.mark_failed("DEAD")

        states = ctx.all_sub_item_states()
        assert len(states) == 2
        by_id = {s["sub_id"]: s for s in states}
        assert by_id["a"]["url"] == "http://a.com"
        assert by_id["a"]["alive"] is True
        assert by_id["b"]["url"] == "http://b.com"
        assert by_id["b"]["alive"] is False


class TestNotesRoundtrip:
    def test_sub_items_persist_to_notes_json(self, tmp_path):
        """Sub-item state survives write → read → restore cycle."""
        ctx = _make_ctx(tmp_path)
        s1 = ctx.sub_item("cite-1")
        s1.record(url="http://a.com", alive=True)
        s1.mark_success()
        s2 = ctx.sub_item("cite-2")
        s2.record(url="http://b.com", alive=False)
        s2.mark_failed("DEAD_LINK")
        ctx.flush_notes()

        # Read raw notes.json
        notes_path = ctx.sample_dir / "notes.json"
        raw = json.loads(notes_path.read_text())

        assert "sub_items" in raw
        assert raw["sub_items"]["cite-1"]["status"] == "success"
        assert raw["sub_items"]["cite-1"]["state"]["url"] == "http://a.com"
        assert raw["sub_items"]["cite-2"]["status"] == "failed"
        assert "DEAD_LINK" in raw["sub_items"]["cite-2"]["errors"]

    def test_sub_items_restored_on_resume(self, tmp_path):
        """BaseRunner restores sub_items from existing notes on resume."""
        # First run: create sub-items and flush
        ctx = _make_ctx(tmp_path)
        s1 = ctx.sub_item("cite-1")
        s1.record(url="http://a.com", alive=True)
        s1.mark_success()
        s2 = ctx.sub_item("cite-2")
        s2.record(url="http://b.com")
        s2.mark_failed("TIMEOUT")
        ctx._notes.steps_completed.append("verify_links")
        ctx.flush_notes()

        # Second run: BaseRunner should restore sub_items
        call_log = []

        async def verify_step(ctx2: SampleContext) -> None:
            call_log.append("verify")
            # cite-1 should be in completed set
            assert "cite-1" in ctx2.completed_sub_items()
            assert "cite-2" not in ctx2.completed_sub_items()
            # State should be accessible
            states = ctx2.all_sub_item_states()
            assert len(states) == 2

        steps = [
            StepDefinition(name="verify_links", fn=AsyncMock()),
            StepDefinition(name="compile", fn=verify_step),
        ]
        runner = _make_runner(steps, SCHEMA, tmp_path)
        result = asyncio.run(runner.run_sample({"sample_id": "s1"}))

        # verify_links was skipped (already completed), compile was called
        assert call_log == ["verify"]
        assert result["status"] == "success"

    def test_sub_items_with_step_runner_end_to_end(self, tmp_path):
        """Full end-to-end: step creates sub-items, notes persist correctly."""

        async def process_citations(ctx: SampleContext) -> None:
            citations = ["ref-1", "ref-2", "ref-3"]
            for cid in citations:
                if cid in ctx.completed_sub_items():
                    continue
                sub = ctx.sub_item(cid)
                if cid == "ref-2":
                    sub.mark_failed("DEAD_LINK")
                else:
                    sub.record(url=f"http://{cid}.com", alive=True)
                    sub.mark_success()
            ctx.flush_notes()

        async def summarize(ctx: SampleContext) -> None:
            states = ctx.all_sub_item_states()
            alive = sum(1 for s in states if s.get("alive"))
            ctx.record(total_refs=str(len(states)), alive_refs=str(alive))

        steps = [
            StepDefinition(name="process_citations", fn=process_citations),
            StepDefinition(name="summarize", fn=summarize),
        ]
        schema = ["sample_id", "total_refs", "alive_refs", "status", "error"]
        runner = _make_runner(steps, schema, tmp_path)

        result = asyncio.run(runner.run_sample({"sample_id": "wiki-1"}))

        assert result["status"] == "success"
        assert result["total_refs"] == "3"
        assert result["alive_refs"] == "2"

        # Verify notes.json structure
        notes = json.loads(
            (tmp_path / "evidence" / "wiki-1" / "notes.json").read_text()
        )
        assert len(notes["sub_items"]) == 3
        assert notes["sub_items"]["ref-1"]["status"] == "success"
        assert notes["sub_items"]["ref-2"]["status"] == "failed"
        assert notes["sub_items"]["ref-3"]["status"] == "success"
