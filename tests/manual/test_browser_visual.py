"""Manual visual test for BrowserAdapter.

Run with:
    PYTHONPATH=src python tests/manual/test_browser_visual.py [scenario]

Scenarios:
    open        Open example.com, take viewport + tiled screenshots (default)
    404         Trigger PageNotFoundError on a non-existent page
    login       Trigger LoginRedirectError on a page requiring auth

Screenshots are saved to tests/manual/_output/ (git-ignored).
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

# Allow running from repo root with PYTHONPATH=src
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from evidence_collector.adapters.browser import (
    BrowserAdapter,
    LoginRedirectError,
    PageNotFoundError,
)

OUTPUT_DIR = Path(__file__).parent / "_output"

SCENARIOS = {}


def scenario(name: str):
    """Register a scenario function."""
    def decorator(fn):
        SCENARIOS[name] = fn
        return fn
    return decorator


@scenario("open")
async def test_open(adapter: BrowserAdapter) -> None:
    """Open a page, print info, take screenshots."""
    page = await adapter.open("https://example.com")
    print(f"  Title: {await page.title()}")
    print(f"  URL:   {page.url}")

    await adapter.screenshot(page, OUTPUT_DIR / "viewport.png", mode="viewport")
    print(f"  Saved: {OUTPUT_DIR / 'viewport.png'}")

    await adapter.screenshot(page, OUTPUT_DIR / "tiled.png", mode="tiled")
    tiles = sorted(OUTPUT_DIR.glob("tiled_*.png"))
    for t in tiles:
        print(f"  Saved: {t}")

    print("\n  Open the _output/ folder to inspect screenshots.")


@scenario("404")
async def test_404(adapter: BrowserAdapter) -> None:
    """Expect PageNotFoundError on a non-existent page."""
    url = "https://github.com/thisrepo/doesnotexist-xyz-404-test"
    print(f"  Opening {url} ...")
    try:
        await adapter.open(url)
        print("  UNEXPECTED: No error raised — 404 detection may need tuning for this site.")
    except PageNotFoundError as exc:
        print(f"  PageNotFoundError raised (expected): {exc}")
    except LoginRedirectError as exc:
        print(f"  LoginRedirectError raised (site redirected to login): {exc}")


@scenario("login")
async def test_login_redirect(adapter: BrowserAdapter) -> None:
    """Expect LoginRedirectError on an auth-gated page."""
    url = "https://github.com/settings/profile"
    print(f"  Opening {url} ...")
    try:
        await adapter.open(url)
        print("  UNEXPECTED: No error raised — you may already be logged in via profile_dir.")
    except LoginRedirectError as exc:
        print(f"  LoginRedirectError raised (expected): {exc}")


def print_usage() -> None:
    print("Usage: PYTHONPATH=src python tests/manual/test_browser_visual.py [scenario]\n")
    print("Scenarios:")
    for name, fn in SCENARIOS.items():
        print(f"  {name:10s}  {fn.__doc__}")
    print()


async def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "open"

    if name in ("-h", "--help", "help"):
        print_usage()
        return

    if name not in SCENARIOS:
        print(f"Unknown scenario: {name!r}\n")
        print_usage()
        sys.exit(1)

    # Fresh output dir each run
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    adapter = BrowserAdapter(headless=False)
    try:
        print(f"\n--- Scenario: {name} ---\n")
        await SCENARIOS[name](adapter)
        print()
        input("Press Enter to close the browser...")
    finally:
        await adapter.close()
        print("Browser closed.")


if __name__ == "__main__":
    asyncio.run(main())
