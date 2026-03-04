"""GitHub checks + CI + Jira traversal playbook runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseRunner


class GitHubChecksRunner(BaseRunner):
    """Playbook B: PR/commit evidence with checks, CI, and Jira traversal."""

    @property
    def playbook_name(self) -> str:
        return "github-checks"

    def load_samples(self) -> list[dict]:
        # TODO: read CSV/XLSX, validate pr_url or commit_url column
        raise NotImplementedError

    def process_sample(self, sample: dict) -> dict:
        # TODO: open PR/commit, screenshot header, extract creator/approvers/merger,
        #       open checks page, detect pass/fail/optional, screenshot CI details,
        #       detect and follow Jira links, write notes.json
        raise NotImplementedError
