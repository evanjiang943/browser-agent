"""Tests for agent task description models."""

import json

import pytest

from evidence_collector.agent.task import OutputField, TaskDescription, load_task


class TestOutputField:
    def test_defaults(self):
        f = OutputField(name="title", description="Page title")
        assert f.name == "title"
        assert f.required is True

    def test_optional(self):
        f = OutputField(name="notes", description="Extra notes", required=False)
        assert f.required is False


class TestTaskDescription:
    def test_minimal(self):
        t = TaskDescription(
            task_name="test",
            goal="Collect data",
            instructions="Navigate and extract",
            input_columns=["url"],
            output_schema=[OutputField(name="title", description="Title")],
        )
        assert t.task_name == "test"
        assert t.max_turns == 30
        assert t.max_pages_per_sample == 10
        assert t.constraints == []

    def test_full(self):
        t = TaskDescription(
            task_name="full-test",
            goal="Goal",
            instructions="Instructions",
            input_columns=["url", "name"],
            output_schema=[
                OutputField(name="a", description="Field A"),
                OutputField(name="b", description="Field B", required=False),
            ],
            constraints=["screenshot before extract"],
            max_pages_per_sample=5,
            max_turns=20,
        )
        assert len(t.output_schema) == 2
        assert t.constraints == ["screenshot before extract"]
        assert t.max_turns == 20

    def test_validation_error(self):
        with pytest.raises(Exception):
            TaskDescription(task_name="bad")  # missing required fields


class TestLoadTask:
    def test_load_json(self, tmp_path):
        task_file = tmp_path / "task.json"
        task_file.write_text(json.dumps({
            "task_name": "test-task",
            "goal": "Test goal",
            "instructions": "Test instructions",
            "input_columns": ["url"],
            "output_schema": [{"name": "title", "description": "Page title"}],
        }))
        t = load_task(task_file)
        assert t.task_name == "test-task"
        assert len(t.output_schema) == 1
        assert t.output_schema[0].name == "title"

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_task("/nonexistent/task.json")

    def test_load_invalid_json(self, tmp_path):
        task_file = tmp_path / "bad.json"
        task_file.write_text("{invalid}")
        with pytest.raises(Exception):
            load_task(task_file)


class TestExampleTaskFiles:
    """Validate the task YAML files in examples/tasks/ load correctly."""

    TASK_FILES = [
        ("examples/tasks/github-checks.yaml", "github-checks", ["pr_url"], 10, 8),
        ("examples/tasks/code-recency.yaml", "code-recency", ["repo_url", "code_string_hash", "since_days"], 14, 9),
        ("examples/tasks/wikipedia-citations.yaml", "wikipedia-citations", ["url"], 13, 11),
    ]

    @pytest.mark.parametrize("path,name,input_cols,total_fields,required_fields", TASK_FILES)
    def test_load_and_validate(self, path, name, input_cols, total_fields, required_fields):
        from pathlib import Path
        task_path = Path(__file__).parent.parent / path
        if not task_path.exists():
            pytest.skip(f"{path} not found")
        t = load_task(task_path)
        assert t.task_name == name
        assert t.input_columns == input_cols
        assert len(t.output_schema) == total_fields
        required = [f for f in t.output_schema if f.required]
        assert len(required) == required_fields
        # Verify no infrastructure fields in output schema
        schema_names = {f.name for f in t.output_schema}
        assert "sample_id" not in schema_names
        assert "status" not in schema_names
        assert "error" not in schema_names
