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

- **`runners/`** — One runner per playbook (A–E): tickets, github_checks, linkedin_enrich, code_recency, erp_analogue
- **`adapters/`** — Playwright wrappers for specific systems (browser.py is the base; github.py, jira_like.py, linkedin.py)
- **`evidence/`** — Naming conventions (`naming.py`), run manifest + sample notes models (`manifest.py`), JSONL logger (`logging.py`)
- **`io/`** — Directory setup and notes.json I/O (`paths.py`), spreadsheet reading (`spreadsheets.py`)
- **`config.py`** — Pydantic config models: BrowserConfig, ThrottleConfig, ScreenshotConfig, RunConfig

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

Early MVP. Implemented: naming, manifest/logging, paths/notes, config models. Most adapters, runners, CLI commands, and IO utilities are stubs (`NotImplementedError`). See `docs/` for full specs.
