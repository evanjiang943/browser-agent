"""Tool definitions for the LLM agent.

Each tool wraps BrowserAdapter / Playwright primitives. The registry maps
tool names to async handler functions, and build_tool_schemas() produces
the Claude tool-use JSON format.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from evidence_collector.adapters.browser import (
    LoginRedirectError,
    PageNotFoundError,
    find_links_matching,
)
from evidence_collector.evidence.naming import screenshot_filename

if TYPE_CHECKING:
    from evidence_collector.agent.loop import AgentContext

logger = logging.getLogger(__name__)


# ── Tool implementations ─────────────────────────────────────────────────


async def open_url(ctx: AgentContext, url: str) -> dict[str, Any]:
    if len(ctx.pages) >= ctx.task.max_pages_per_sample:
        return {"error": "MAX_PAGES_REACHED", "limit": ctx.task.max_pages_per_sample}
    try:
        page = await ctx.browser.open(url)
    except LoginRedirectError as exc:
        return {"error": "AUTH_REQUIRED", "message": str(exc)}
    except PageNotFoundError as exc:
        return {"error": "PAGE_NOT_FOUND", "message": str(exc)}
    except Exception as exc:
        return {"error": "NAVIGATION_FAILED", "message": str(exc)}

    page_id = f"page_{len(ctx.pages)}"
    ctx.pages[page_id] = page
    title = await page.title()
    return {"page_id": page_id, "final_url": page.url, "title": title}


async def click_element(ctx: AgentContext, page_id: str, selector: str) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    try:
        await page.click(selector, timeout=ctx.browser.timeout)
        return {"success": True}
    except Exception as exc:
        return {"error": "CLICK_FAILED", "message": str(exc)}


async def scroll_page(
    ctx: AgentContext, page_id: str, direction: str, amount_px: int | None = None
) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    vp = page.viewport_size or {"height": 800}
    px = amount_px or vp["height"]
    delta = px if direction == "down" else -px
    try:
        await page.evaluate(f"window.scrollBy(0, {delta})")
        scroll_y = await page.evaluate("window.scrollY")
        scroll_height = await page.evaluate("document.body.scrollHeight")
        return {"scroll_y": scroll_y, "scroll_height": scroll_height}
    except Exception as exc:
        return {"error": "SCROLL_FAILED", "message": str(exc)}


async def close_page(ctx: AgentContext, page_id: str) -> dict[str, Any]:
    page = ctx.pages.pop(page_id, None)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    await page.close()
    return {"success": True}


async def read_page_text(
    ctx: AgentContext, page_id: str, max_chars: int | None = None
) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    try:
        text = await page.inner_text("body")
        truncated = False
        if max_chars and len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        return {"text": text, "truncated": truncated}
    except Exception as exc:
        return {"error": "READ_FAILED", "message": str(exc)}


async def query_selector_text(
    ctx: AgentContext, page_id: str, selector: str
) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    try:
        el = await page.query_selector(selector)
        if el is None:
            return {"found": False, "text": "", "href": None, "tag": None}
        text = (await el.inner_text()).strip()
        href = await el.get_attribute("href")
        tag = await el.evaluate("el => el.tagName.toLowerCase()")
        return {"found": True, "text": text, "href": href, "tag": tag}
    except Exception as exc:
        return {"error": "QUERY_FAILED", "message": str(exc)}


async def query_selector_all_text(
    ctx: AgentContext, page_id: str, selector: str, limit: int | None = None
) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    try:
        elements = await page.query_selector_all(selector)
        actual_limit = limit or 50
        items = []
        for el in elements[:actual_limit]:
            text = (await el.inner_text()).strip()
            href = await el.get_attribute("href")
            tag = await el.evaluate("el => el.tagName.toLowerCase()")
            items.append({"text": text, "href": href, "tag": tag})
        return {"count": len(elements), "items": items}
    except Exception as exc:
        return {"error": "QUERY_FAILED", "message": str(exc)}


async def tool_find_links(
    ctx: AgentContext, page_id: str, url_pattern: str
) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    try:
        links = await find_links_matching(page, [url_pattern])
        return {"links": links}
    except Exception as exc:
        return {"error": "FIND_LINKS_FAILED", "message": str(exc)}


async def get_page_url(ctx: AgentContext, page_id: str) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    return {"url": page.url}


async def evaluate_js(
    ctx: AgentContext, page_id: str, expression: str
) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    try:
        result = await page.evaluate(expression)
        return {"result": result}
    except Exception as exc:
        return {"error": "EVAL_FAILED", "message": str(exc)}


async def take_screenshot(
    ctx: AgentContext, page_id: str, label: str, mode: str | None = None
) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    shot_mode = mode or ctx.screenshot_mode
    filename = screenshot_filename(ctx.sample_id, "web", label)
    shot_dir = ctx.sample_dir / "screenshots"
    shot_path = shot_dir / filename
    try:
        await ctx.browser.screenshot(page, shot_path, mode=shot_mode)
        ctx.notes.screenshots.append(filename)
        ctx.last_screenshot_page_id = page_id
        return {"filename": filename, "path": str(shot_path)}
    except Exception as exc:
        return {"error": "SCREENSHOT_FAILED", "message": str(exc)}


async def save_download(
    ctx: AgentContext, page_id: str, click_selector: str, filename: str
) -> dict[str, Any]:
    page = ctx.pages.get(page_id)
    if page is None:
        return {"error": "INVALID_PAGE_ID", "page_id": page_id}
    dest = ctx.sample_dir / "downloads" / filename
    try:
        await ctx.browser.download_file(page, click_selector, dest)
        ctx.notes.downloads.append(filename)
        return {"path": str(dest), "size_bytes": dest.stat().st_size}
    except Exception as exc:
        return {"error": "DOWNLOAD_FAILED", "message": str(exc)}


async def record_field(
    ctx: AgentContext, field_name: str, value: str
) -> dict[str, Any]:
    valid_names = {f.name for f in ctx.task.output_schema}
    if field_name not in valid_names:
        return {
            "error": "INVALID_FIELD",
            "message": f"'{field_name}' is not in the output schema. Valid fields: {sorted(valid_names)}",
        }
    # Record the current page URL for provenance
    page_url = None
    if ctx.pages:
        last_page_id = list(ctx.pages.keys())[-1]
        page_url = ctx.pages[last_page_id].url
    ctx.recorded_fields[field_name] = value
    ctx.field_provenance[field_name] = page_url
    return {"success": True}


async def get_required_fields(ctx: AgentContext) -> dict[str, Any]:
    filled = []
    missing = []
    for f in ctx.task.output_schema:
        if ctx.recorded_fields.get(f.name):
            filled.append(f.name)
        elif f.required:
            missing.append(f.name)
    return {"filled": filled, "missing": missing}


async def get_recorded_fields(ctx: AgentContext) -> dict[str, Any]:
    return {"fields": dict(ctx.recorded_fields)}


# ── Tool registry ────────────────────────────────────────────────────────

# Maps tool name -> (handler, param extraction function)
# Handler signature: async (ctx, **params) -> dict

_TOOL_HANDLERS: dict[str, Any] = {
    "open_url": open_url,
    "click_element": click_element,
    "scroll_page": scroll_page,
    "close_page": close_page,
    "read_page_text": read_page_text,
    "query_selector_text": query_selector_text,
    "query_selector_all_text": query_selector_all_text,
    "find_links": tool_find_links,
    "get_page_url": get_page_url,
    "evaluate_js": evaluate_js,
    "take_screenshot": take_screenshot,
    "save_download": save_download,
    "record_field": record_field,
    "get_required_fields": get_required_fields,
    "get_recorded_fields": get_recorded_fields,
}


async def execute_tool(ctx: AgentContext, tool_name: str, params: dict) -> dict:
    """Dispatch a tool call to the appropriate handler."""
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return {"error": "UNKNOWN_TOOL", "tool": tool_name}

    try:
        return await _dispatch_tool(ctx, tool_name, handler, params)
    except Exception as exc:
        return {"error": "TOOL_ERROR", "tool": tool_name, "message": str(exc)}


async def _dispatch_tool(
    ctx: AgentContext, tool_name: str, handler: Any, params: dict[str, Any]
) -> dict[str, Any]:
    """Route params and call the handler."""
    if tool_name == "open_url":
        return await handler(ctx, url=params["url"])
    elif tool_name == "click_element":
        return await handler(ctx, page_id=params["page_id"], selector=params["selector"])
    elif tool_name == "scroll_page":
        return await handler(
            ctx, page_id=params["page_id"],
            direction=params["direction"],
            amount_px=params.get("amount_px"),
        )
    elif tool_name == "close_page":
        return await handler(ctx, page_id=params["page_id"])
    elif tool_name == "read_page_text":
        return await handler(ctx, page_id=params["page_id"], max_chars=params.get("max_chars"))
    elif tool_name == "query_selector_text":
        return await handler(ctx, page_id=params["page_id"], selector=params["selector"])
    elif tool_name == "query_selector_all_text":
        return await handler(
            ctx, page_id=params["page_id"],
            selector=params["selector"],
            limit=params.get("limit"),
        )
    elif tool_name == "find_links":
        return await handler(ctx, page_id=params["page_id"], url_pattern=params["url_pattern"])
    elif tool_name == "get_page_url":
        return await handler(ctx, page_id=params["page_id"])
    elif tool_name == "evaluate_js":
        return await handler(ctx, page_id=params["page_id"], expression=params["expression"])
    elif tool_name == "take_screenshot":
        return await handler(
            ctx, page_id=params["page_id"],
            label=params["label"],
            mode=params.get("mode"),
        )
    elif tool_name == "save_download":
        return await handler(
            ctx, page_id=params["page_id"],
            click_selector=params["click_selector"],
            filename=params["filename"],
        )
    elif tool_name == "record_field":
        return await handler(ctx, field_name=params["field_name"], value=params["value"])
    elif tool_name in ("get_required_fields", "get_recorded_fields"):
        return await handler(ctx)
    else:
        return {"error": "UNKNOWN_TOOL", "tool": tool_name}


# ── Schema generation ────────────────────────────────────────────────────


def build_tool_schemas() -> list[dict]:
    """Generate Claude tool-use JSON schemas for all agent tools."""
    return [
        {
            "name": "open_url",
            "description": "Open a URL in the browser. Returns page_id for subsequent operations.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to"},
                },
                "required": ["url"],
            },
        },
        {
            "name": "click_element",
            "description": "Click an element on the page identified by CSS selector.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to interact with"},
                    "selector": {"type": "string", "description": "CSS selector of the element to click"},
                },
                "required": ["page_id", "selector"],
            },
        },
        {
            "name": "scroll_page",
            "description": "Scroll the page up or down.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to scroll"},
                    "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction"},
                    "amount_px": {"type": "integer", "description": "Pixels to scroll (default: viewport height)"},
                },
                "required": ["page_id", "direction"],
            },
        },
        {
            "name": "close_page",
            "description": "Close a page and free resources.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to close"},
                },
                "required": ["page_id"],
            },
        },
        {
            "name": "read_page_text",
            "description": "Read the visible text content of the page body.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to read"},
                    "max_chars": {"type": "integer", "description": "Maximum characters to return (default: unlimited)"},
                },
                "required": ["page_id"],
            },
        },
        {
            "name": "query_selector_text",
            "description": "Get the text content, href, and tag of a single element matching a CSS selector.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to query"},
                    "selector": {"type": "string", "description": "CSS selector to match"},
                },
                "required": ["page_id", "selector"],
            },
        },
        {
            "name": "query_selector_all_text",
            "description": "Get text, href, and tag for all elements matching a CSS selector.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to query"},
                    "selector": {"type": "string", "description": "CSS selector to match"},
                    "limit": {"type": "integer", "description": "Max elements to return (default: 50)"},
                },
                "required": ["page_id", "selector"],
            },
        },
        {
            "name": "find_links",
            "description": "Find all links on the page whose href matches a regex pattern.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to search"},
                    "url_pattern": {"type": "string", "description": "Regex pattern to match against href values"},
                },
                "required": ["page_id", "url_pattern"],
            },
        },
        {
            "name": "get_page_url",
            "description": "Get the current URL of a page.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to check"},
                },
                "required": ["page_id"],
            },
        },
        {
            "name": "evaluate_js",
            "description": "Execute a JavaScript expression on the page and return the result.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to run JS on"},
                    "expression": {"type": "string", "description": "JavaScript expression to evaluate"},
                },
                "required": ["page_id", "expression"],
            },
        },
        {
            "name": "take_screenshot",
            "description": "Take a screenshot of the page. Screenshots are saved as evidence.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page to screenshot"},
                    "label": {"type": "string", "description": "Descriptive label for the screenshot (e.g. 'pr-overview', 'ci-results')"},
                    "mode": {"type": "string", "enum": ["viewport", "tiled"], "description": "Screenshot mode (default: viewport)"},
                },
                "required": ["page_id", "label"],
            },
        },
        {
            "name": "save_download",
            "description": "Click an element to trigger a download and save the file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The page containing the download link"},
                    "click_selector": {"type": "string", "description": "CSS selector to click to trigger download"},
                    "filename": {"type": "string", "description": "Filename to save the download as"},
                },
                "required": ["page_id", "click_selector", "filename"],
            },
        },
        {
            "name": "record_field",
            "description": "Record a value for an output field. Only fields defined in the output schema are accepted.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string", "description": "Name of the output field"},
                    "value": {"type": "string", "description": "The value to record"},
                },
                "required": ["field_name", "value"],
            },
        },
        {
            "name": "get_required_fields",
            "description": "Check which output fields have been filled and which are still missing.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "get_recorded_fields",
            "description": "Get all currently recorded field values.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    ]
