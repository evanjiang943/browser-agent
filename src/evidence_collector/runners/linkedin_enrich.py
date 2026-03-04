"""LinkedIn CSV enrichment playbook runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseRunner


class LinkedInEnrichRunner(BaseRunner):
    """Playbook C: enrich CSV with LinkedIn profile data."""

    def load_samples(self) -> list[dict]:
        # TODO: read CSV/XLSX, validate 'name' column exists
        raise NotImplementedError

    def process_sample(self, sample: dict) -> dict:
        # TODO: search LinkedIn for profile, pick best match,
        #       extract linkedin_url/school/current_company/tenure,
        #       screenshot profile header, write notes.json
        raise NotImplementedError
