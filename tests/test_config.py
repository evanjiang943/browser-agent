"""Tests for config models and load_config."""

import json

import pytest

from evidence_collector.config import (
    AgentConfig,
    BrowserConfig,
    RunConfig,
    ScreenshotConfig,
    ThrottleConfig,
    load_config,
)


class TestBrowserConfig:
    def test_defaults(self):
        c = BrowserConfig()
        assert c.headless is True
        assert c.timeout_ms == 30_000
        assert c.profile_dir is None

    def test_custom(self):
        c = BrowserConfig(headless=False, timeout_ms=5000, profile_dir="/tmp/prof")
        assert c.headless is False
        assert c.timeout_ms == 5000
        assert c.profile_dir == "/tmp/prof"


class TestThrottleConfig:
    def test_defaults(self):
        c = ThrottleConfig()
        assert c.max_pages_per_minute == 20
        assert c.retry_attempts == 3
        assert c.backoff_base_seconds == 2.0


class TestScreenshotConfig:
    def test_defaults(self):
        c = ScreenshotConfig()
        assert c.mode == "viewport"
        assert c.quality == 90


class TestAgentConfig:
    def test_defaults(self):
        c = AgentConfig()
        assert c.model == "claude-sonnet-4-20250514"
        assert c.max_turns == 30
        assert c.temperature == 0.0
        assert c.api_key_env == "ANTHROPIC_API_KEY"

    def test_custom(self):
        c = AgentConfig(model="claude-haiku-4-5-20251001", max_turns=10, temperature=0.5)
        assert c.model == "claude-haiku-4-5-20251001"
        assert c.max_turns == 10


class TestRunConfig:
    def test_defaults(self):
        c = RunConfig()
        assert isinstance(c.browser, BrowserConfig)
        assert isinstance(c.throttle, ThrottleConfig)
        assert isinstance(c.screenshot, ScreenshotConfig)
        assert isinstance(c.agent, AgentConfig)
        assert c.concurrency == 1

    def test_nested_override(self):
        c = RunConfig(browser=BrowserConfig(headless=False), concurrency=4)
        assert c.browser.headless is False
        assert c.concurrency == 4

    def test_model_dump_roundtrip(self):
        original = RunConfig(
            browser=BrowserConfig(timeout_ms=5000),
            throttle=ThrottleConfig(retry_attempts=5),
        )
        data = original.model_dump()
        restored = RunConfig.model_validate(data)
        assert restored == original


class TestLoadConfig:
    def test_none_returns_defaults(self):
        c = load_config(None)
        assert c == RunConfig()

    def test_json_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"browser": {"headless": False}, "concurrency": 3})
        )
        c = load_config(str(config_file))
        assert c.browser.headless is False
        assert c.concurrency == 3
        # Non-overridden values keep defaults
        assert c.throttle == ThrottleConfig()

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.json")
