"""LinkedIn adapter — profile search and extraction."""

from __future__ import annotations


class LinkedInAdapter:
    """LinkedIn-specific browser interactions for profile search and extraction."""

    def __init__(self, browser_adapter) -> None:
        self.browser = browser_adapter

    async def search_profile(self, name: str, company_hint: str | None = None, location_hint: str | None = None) -> str | None:
        """Search for a LinkedIn profile and return the best match URL."""
        # TODO: perform search, rank results, return best match URL
        raise NotImplementedError

    async def extract_profile_fields(self) -> dict:
        """Extract linkedin_url, school, current_company, tenure from profile page."""
        # TODO: extract profile fields using selectors or text parsing
        raise NotImplementedError
