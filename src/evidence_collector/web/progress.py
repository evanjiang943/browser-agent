"""Progress events for streaming agent status to the frontend."""

from __future__ import annotations

from pydantic import BaseModel


class ProgressEvent(BaseModel):
    """A progress event emitted by the agent during execution."""

    event_type: str  # tool_call | sample_start | sample_end | error
    sample_id: str = ""
    sample_index: int = 0
    total_samples: int = 0
    tool_name: str = ""
    tool_params: dict = {}
    tool_result: dict = {}
    message: str = ""


_TOOL_TEMPLATES: dict[str, str] = {
    "open_url": "Opening {url}...",
    "click_element": "Clicking element on {page_id}",
    "scroll_page": "Scrolling {direction} on {page_id}",
    "close_page": "Closing {page_id}",
    "read_page_text": "Reading page content...",
    "query_selector_text": "Querying element: {selector}",
    "query_selector_all_text": "Querying elements: {selector}",
    "find_links": "Searching for links matching pattern",
    "get_page_url": "Getting page URL",
    "evaluate_js": "Executing JavaScript",
    "take_screenshot": "Taking screenshot: {label}",
    "save_download": "Downloading file: {filename}",
    "record_field": "Recorded {field_name} = {value}",
    "get_required_fields": "Checking required fields",
    "get_recorded_fields": "Checking recorded fields",
}


def tool_progress_message(tool_name: str, params: dict) -> str:
    """Generate a human-friendly progress message for a tool call."""
    template = _TOOL_TEMPLATES.get(tool_name)
    if template is None:
        return f"Executing {tool_name}"
    try:
        if tool_name == "record_field":
            value = str(params.get("value", ""))
            if len(value) > 60:
                params = {**params, "value": value[:60] + "..."}
        return template.format(**params)
    except KeyError:
        return f"Executing {tool_name}"
