"""LinkedIn CSV enrichment playbook runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import PlaybookRunner


class LinkedInEnrichRunner(PlaybookRunner):
    """Playbook C: enrich CSV with LinkedIn profile data."""

    @property
    def playbook_name(self) -> str:
        return "linkedin-enrich"

    def load_samples(self) -> list[dict]:
        # TODO: read CSV/XLSX, validate 'name' column exists
        raise NotImplementedError

    def process_sample(self, sample: dict) -> dict:
        # TODO: search LinkedIn for profile, pick best match,
        #       extract linkedin_url/school/current_company/tenure,
        #       screenshot profile header, write notes.json
        raise NotImplementedError
