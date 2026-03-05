# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
# Run all tests
PYTHONPATH=src python -m pytest tests/ -v

# Run a single test file
PYTHONPATH=src python -m pytest tests/test_task.py -v

# Run a single test
PYTHONPATH=src python -m pytest tests/test_task.py::TestExampleTaskFiles -v

# pip install -e . requires hatchling; currently broken in this env — use PYTHONPATH instead
```

No linter or formatter is configured.

## Architecture

**LLM-driven browser agent for audit evidence collection.** Claude decides navigation and extraction at runtime via tool calling. The user describes what to collect; the agent figures out how.

### Core Flow

1. User provides a CSV/XLSX + task description (natural language or YAML)
2. `AgentRunner` loads samples, sets up browser, creates output directories
3. For each sample, `run_agent_for_sample()` drives a Claude API loop with 15 browser tools
4. The agent navigates, screenshots, extracts data, records fields via `record_field`
5. Per-sample: `notes.json`, `agent_trace.jsonl`, `report.md`, screenshots, downloads
6. Run-level: `results.csv`, `run_manifest.json`, `report.md` (visual audit summary)

### Key Modules

- **`agent/task.py`** — `TaskDescription`, `OutputField`, `load_task()` from YAML/JSON
- **`agent/tools.py`** — 15 tool functions + `TOOL_REGISTRY` + `build_tool_schemas()` + `execute_tool()`
- **`agent/loop.py`** — `AgentContext`, `run_agent_for_sample()` (Claude API loop with tool dispatch)
- **`agent/runner.py`** — `AgentRunner` (concurrency, throttle, circuit breaker, resumability)
- **`agent/report.py`** — `generate_sample_report()`, `generate_run_report()` (markdown with inline screenshots)
- **`agent/prompts.py`** — `build_system_prompt()`, `format_initial_prompt()`, `resume_context_message()`
- **`agent/planner.py`** — `plan_task()` (natural language → `TaskDescription` via Claude)
- **`agent/audit.py`** — `ToolCallRecord`, `save_agent_trace()`, `load_agent_trace()`, `verify_trace()`
- **`adapters/browser.py`** — `BrowserAdapter` (Playwright), extraction rules, link finding, login/404 detection
- **`evidence/`** — Naming (`naming.py`), manifest/notes models (`manifest.py`), JSONL logger (`logging.py`)
- **`io/`** — Directory setup (`paths.py`), spreadsheet reading (`spreadsheets.py`), CSV output (`csv_utils.py`)
- **`config.py`** — Pydantic config: BrowserConfig, ThrottleConfig, ScreenshotConfig, AgentConfig, RunConfig
- **`utils/`** — `time.py`, `text.py`, `throttling.py`, `retry.py`
- **`web/`** — FastAPI app, WebSocket handler, chat planner, session management, progress streaming

### Agent Tools (15)

| Category | Tools |
|----------|-------|
| Navigation | `open_url`, `click_element`, `scroll_page`, `close_page` |
| Observation | `read_page_text`, `query_selector_text`, `query_selector_all_text`, `find_links`, `get_page_url`, `evaluate_js` |
| Evidence | `take_screenshot`, `save_download`, `record_field` |
| State | `get_required_fields`, `get_recorded_fields` |

### Output Structure

```
out_dir/
├── report.md               # Visual audit report with screenshots
├── results.csv
├── run_manifest.json
├── run_log.jsonl
└── evidence/<task_name>/
    └── <sample_id>/
        ├── report.md           # Per-sample visual walkthrough
        ├── notes.json
        ├── agent_trace.jsonl
        ├── screenshots/
        └── downloads/
```

### Patterns

- **Atomic writes** — tempfile + `os.replace()` for all state files
- **Deterministic sample IDs** — from primary_key > URL > name fields via `naming.py`
- **Resumability** — `notes.json` tracks completion; agent skips completed samples on rerun
- **Schema enforcement** — `record_field` rejects unknown fields; post-loop validation checks required fields
- **Auditability** — `agent_trace.jsonl` logs every tool call; `verify_trace()` checks provenance; `report.md` provides visual summary
- **Pydantic models** — all structured data uses Pydantic v2

## Repository Layout

```
├── README.md               # Product description and tech specs
├── CLAUDE.md               # This file
├── examples/               # Example CSVs and task YAML files
│   ├── tasks/              # Task definitions (github-checks, code-recency, wikipedia-citations)
│   └── *.csv               # Sample input data
├── src/evidence_collector/ # Source code
├── tests/                  # Unit tests (217 passing)
│   └── manual/             # Visual/integration tests (excluded from pytest)
├── pyproject.toml
└── requirements.txt
```

## Development Status

**217 tests passing.** Agent, CLI, and web UI fully implemented.

### Not yet implemented
- CLI `resume` command (lists incomplete samples but doesn't re-run)
- Integration testing with real Claude API calls

Note: `tests/manual/` is excluded from pytest via `--ignore=tests/manual` in pyproject.toml.
