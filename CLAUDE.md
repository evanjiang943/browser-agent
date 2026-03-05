# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
# Run all tests (package not installed via pip, use PYTHONPATH)
PYTHONPATH=src python -m pytest tests/ -v

# Run a single test file
PYTHONPATH=src python -m pytest tests/test_manifest.py -v

# Run a single test function
PYTHONPATH=src python -m pytest tests/test_manifest.py::test_notes_roundtrip -v

# Install in editable mode (requires hatchling; currently broken in this env, use PYTHONPATH instead)
pip install -e .
```

No linter or formatter is configured.

## Architecture

**Browser-based audit evidence collector** — automates gathering screenshots, downloads, and extracted data from web tools (Jira, GitHub, LinkedIn, ERPs) for compliance audits.

### Core Flow

1. User invokes CLI: `evidence-collector run <playbook> --input file.csv --out dir/`
2. A **Runner** (inherits `runners/base.py:BaseRunner`) loads samples from the input spreadsheet
3. For each sample, the runner uses **Adapters** (`adapters/`) to drive Playwright browser sessions
4. Evidence artifacts (screenshots, downloads, extracted data) are saved per-sample
5. A `run_manifest.json`, `run_log.jsonl`, and `results.csv` summarize the run

### Key Modules

- **`runners/base.py`** — `BaseRunner` (generic step engine with `StepDefinition`, `SampleContext`, `SubItemContext`) + `PlaybookRunner` (shared orchestration base class). Subclasses only define: `playbook_name`, `result_columns`, `load_samples()`, `process_sample()`, `create_adapters()`
- **`runners/`** — Implemented: `tickets.py` (step-based via BaseRunner), `github_checks.py`, `code_recency.py` (both PlaybookRunner subclasses). Stubs: `linkedin_enrich.py`, `erp_analogue.py`
- **`adapters/browser.py`** — `BrowserAdapter` (Playwright Chromium), `ExtractionRule` + `extract_fields()` (declarative extraction), `find_links_matching()`, `verify_url()`, login/404 detection
- **`adapters/github.py`** — `GitHubAdapter`: PR metadata extraction, checks extraction, blame dates, code search, commit diff summary, ticket link discovery. Selectors validated against real GitHub DOM
- **`adapters/`** — Stubs: `jira_like.py`, `linkedin.py`
- **`evidence/`** — Naming conventions (`naming.py`), run manifest + sample notes models (`manifest.py`), JSONL logger (`logging.py`)
- **`io/`** — Directory setup and notes.json I/O (`paths.py`), spreadsheet reading (`spreadsheets.py`), CSV output (`csv_utils.py`)
- **`config.py`** — Pydantic config models: BrowserConfig, ThrottleConfig, ScreenshotConfig, RunConfig; `load_config()` supports JSON and optional YAML
- **`utils/`** — `time.py` (timestamps, `is_within_window`), `text.py` (whitespace normalization, Jira/Linear URL extraction, ticket ID parsing), `throttling.py` (rate limiter, circuit breaker), `retry.py` (async/sync retry with backoff)

### Output Directory Structure

```
out_dir/
├── run_manifest.json
├── run_log.jsonl
├── results.csv
└── evidence/<playbook>/
    └── <sample_id>/
        ├── notes.json          # SampleNotes: status, steps, errors, artifact lists
        ├── screenshots/
        └── downloads/
```

### Patterns

- **Atomic writes**: `write_manifest()` and `write_notes()` use tempfile + `os.replace()` for crash safety
- **Deterministic sample IDs**: Generated from primary_key > URL > name fields via `naming.py`
- **Resumability**: `notes.json` per sample tracks completion status; runners skip completed samples on rerun
- **Pydantic models**: All structured data (RunManifest, SampleNotes, configs) uses Pydantic v2

## Development Status

**224 tests passing.** Three of five playbooks are fully implemented and validated against real systems.

### Implemented
- **Foundation**: naming, manifest/logging, paths/notes, config models, BrowserAdapter (open/screenshot/download/login-404 detection), retry/throttling/circuit-breaker, text extraction, CSV output, `is_within_window()`
- **Runner framework**: `BaseRunner` step engine (StepDefinition, SampleContext, SubItemContext, resumability, concurrency, per-step persistence), `PlaybookRunner` shared orchestration
- **Playbook A — Tickets** (`tickets.py`): open ticket URLs, screenshot, extract fields via declarative `ExtractionRule` system
- **Playbook B — GitHub Checks** (`github_checks.py`): 7-step pipeline (open PR, screenshot, extract metadata, navigate to checks tab, extract check results, CI details, Jira traversal). Selectors validated against real facebook/react PRs
- **Playbook D — Code Recency** (`code_recency.py`): 8-step pipeline (code search, blame view, blame date extraction, window check, commit analysis, materiality assessment)
- **GitHubAdapter** (`github.py`): PR metadata, checks, blame dates, code search, commit diff summary, ticket links. Multi-strategy extraction with CSS selectors + text fallbacks, validated against live GitHub DOM
- **CLI**: `run` command dispatches to 3 implemented playbooks, `validate` command checks input schemas

### Stubs remaining
- **Playbook C — LinkedIn Enrich** (`linkedin_enrich.py`): class structure only
- **Playbook E — ERP Analogue** (`erp_analogue.py`): class structure only
- **JiraLikeAdapter** (`jira_like.py`): class structure only
- **LinkedInAdapter** (`linkedin.py`): class structure only
- **CLI `resume` command**: lists incomplete samples but doesn't re-run them

### Deliverables
- `deliverables/github-checks.md` — Full auditor walkthrough with screenshots and real output from a demo run

Note: `tests/manual/` contains visual/integration tests excluded from pytest via `--ignore=tests/manual` in pyproject.toml. Run them manually with explicit paths.
