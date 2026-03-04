"""ERP-analogue form fill + report export playbook runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseRunner


class ERPAnalogueRunner(BaseRunner):
    """Playbook E: fill form, screenshot, download report and attachments."""

    def load_samples(self) -> list[dict]:
        # TODO: read CSV/XLSX with form field values
        raise NotImplementedError

    def process_sample(self, sample: dict) -> dict:
        # TODO: fill form fields, screenshot completed form,
        #       submit and download report, iterate tabs and download attachments,
        #       write notes.json
        raise NotImplementedError
