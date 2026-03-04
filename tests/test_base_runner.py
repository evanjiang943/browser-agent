"""Tests for runners/base.py."""

import json
from pathlib import Path

import pytest

from evidence_collector.runners.base import PlaybookRunner


class ConcreteRunner(PlaybookRunner):
    """Minimal concrete subclass for testing."""

    @property
    def playbook_name(self) -> str:
        return "test-playbook"

    def load_samples(self) -> list[dict]:
        return []

    def process_sample(self, sample: dict) -> dict:
        return {}


class TestPlaybookNameAbstract:
    def test_cannot_instantiate_without_playbook_name(self):
        class Incomplete(PlaybookRunner):
            def load_samples(self):
                return []

            def process_sample(self, sample):
                return {}

        with pytest.raises(TypeError):
            Incomplete(Path("."), Path("."), None)


class TestShouldSkip:
    def _make_runner(self, tmp_path):
        return ConcreteRunner(
            input_path=tmp_path / "input.csv",
            output_dir=tmp_path,
            config=None,
        )

    def test_returns_false_when_no_notes(self, tmp_path):
        runner = self._make_runner(tmp_path)
        assert runner.should_skip({"primary_key": "TICK-1"}) is False

    def test_returns_true_when_success(self, tmp_path):
        runner = self._make_runner(tmp_path)
        sample_dir = (
            tmp_path / "evidence" / "test-playbook" / "tick-1"
        )
        sample_dir.mkdir(parents=True)
        (sample_dir / "notes.json").write_text(json.dumps({"status": "success"}))
        assert runner.should_skip({"primary_key": "TICK-1"}) is True

    def test_returns_false_when_failed(self, tmp_path):
        runner = self._make_runner(tmp_path)
        sample_dir = (
            tmp_path / "evidence" / "test-playbook" / "tick-1"
        )
        sample_dir.mkdir(parents=True)
        (sample_dir / "notes.json").write_text(json.dumps({"status": "failed"}))
        assert runner.should_skip({"primary_key": "TICK-1"}) is False
