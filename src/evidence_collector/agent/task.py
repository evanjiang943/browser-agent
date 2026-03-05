"""Task description models for the LLM agent."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class OutputField(BaseModel):
    """A single field in the output schema."""

    name: str
    description: str
    required: bool = True


class TaskDescription(BaseModel):
    """Declarative description of what the agent should collect."""

    task_name: str
    goal: str
    instructions: str
    input_columns: list[str]
    output_schema: list[OutputField]
    constraints: list[str] = []
    max_pages_per_sample: int = 10
    max_turns: int = 30


def load_task(path: str | Path) -> TaskDescription:
    """Load a TaskDescription from a JSON or YAML file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Task file not found: {path}")

    text = p.read_text()

    if p.suffix == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required to load YAML task files. "
                "Install it with: pip install pyyaml"
            ) from exc
        data = yaml.safe_load(text)

    return TaskDescription.model_validate(data)
