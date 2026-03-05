# Repository Layout — Evidence Collection Agent

## Directory structure

```
evidence-collector/
  CLAUDE.md
  pyproject.toml
  src/
    evidence_collector/
      __init__.py
      cli.py                    # Typer CLI: run, validate, resume commands
      config.py                 # Pydantic config models + load_config()
      runners/
        __init__.py
        base.py                 # BaseRunner (step engine) + PlaybookRunner (shared orchestration)
        tickets.py              # Playbook A: ticket screenshots + extraction
        github_checks.py        # Playbook B: PR checks + CI + Jira traversal
        code_recency.py         # Playbook D: blame + materiality analysis
        linkedin_enrich.py      # Playbook C: stub
        erp_analogue.py         # Playbook E: stub
      adapters/
        __init__.py
        browser.py              # BrowserAdapter, ExtractionRule, extract_fields(), verify_url()
        github.py               # GitHubAdapter: PR metadata, checks, blame, code search
        jira_like.py            # JiraLikeAdapter: stub
        linkedin.py             # LinkedInAdapter: stub
      evidence/
        __init__.py
        naming.py               # generate_sample_id(), screenshot_filename(), safe_folder_name()
        manifest.py             # RunManifest, SampleNotes, SubItemNotes (Pydantic), write_manifest()
        logging.py              # RunLogger: append-only JSONL event log
      io/
        __init__.py
        paths.py                # setup_run_dir(), setup_sample_dir(), read_notes(), write_notes()
        spreadsheets.py         # read_input(), validate_columns(), load_github_samples(), load_code_recency_samples()
        csv_utils.py            # init_results_csv(), append_result_row(), write_results_csv()
      utils/
        __init__.py
        retry.py                # retry_async(), retry_sync() with exponential backoff
        throttling.py           # Throttle (sliding-window rate limiter), CircuitBreaker
        time.py                 # now_iso(), now_filename_stamp(), is_within_window()
        text.py                 # extract_jira_urls(), extract_linear_urls(), extract_ticket_id(), normalize_whitespace()
  tests/
    conftest.py                 # Shared fixtures: mock_browser, mock_page
    test_base_runner.py
    test_browser.py
    test_cli.py
    test_code_recency_runner.py
    test_config.py
    test_csv_utils.py
    test_extraction.py
    test_github_adapter.py
    test_github_adapter_blame.py
    test_github_checks_runner.py
    test_manifest.py
    test_naming.py
    test_retry.py
    test_spreadsheets.py
    test_step_runner.py
    test_text.py
    test_throttling.py
    test_tickets_runner.py
    test_time.py
    manual/                     # Visual/integration tests (excluded from pytest)
      dump_github_dom.py
      github_checks_demo.csv
  examples/
    mock_pr.html                # Mock GitHub PR page for unit tests
    mock_pr_checks.html         # Mock GitHub checks tab for unit tests
  deliverables/
    github-checks.md            # Auditor walkthrough with screenshots
    images/                     # Screenshots from demo run
  docs/
    (this directory)
```

## Technology stack

- **Language**: Python 3.11+
- **Browser automation**: Playwright (async API, Chromium)
- **Config/models**: Pydantic v2 (all structured data)
- **CLI**: Typer
- **Spreadsheet I/O**: csv stdlib + openpyxl for XLSX
- **Testing**: pytest + pytest-asyncio
- **Logging**: JSONL structured logs (custom RunLogger)

## CLI entrypoints

```bash
# Run a playbook
evidence-collector run <playbook> --input <csv> --out <dir> [--headless|--headful] [--profile <dir>]

# Validate input file against playbook schema
evidence-collector validate --playbook <name> --input <csv>

# Resume interrupted run (stub — lists incomplete samples)
evidence-collector resume --run-dir <dir>
```

## Design rules

1. **Playbooks are pure orchestration**: they call adapters + evidence writers, never contain site-specific selectors
2. **Adapters encapsulate site-specific logic**: GitHubAdapter knows GitHub DOM; BrowserAdapter is generic
3. **Evidence output is a contract**: folder structure + naming is deterministic and consistent
4. **Resumability is first-class**: `notes.json` per sample with `steps_completed` tracking; runners skip completed samples on rerun
5. **Multi-strategy extraction**: primary CSS selectors with fallback to text heuristics and regex patterns
6. **Atomic writes**: `write_manifest()` and `write_notes()` use tempfile + `os.replace()` for crash safety

## Per-sample contract

Each sample folder includes:
- `notes.json` — `SampleNotes` Pydantic model: `sample_id`, `status` (pending/success/failed/partial), `steps_completed`, `errors`, `screenshots`, `downloads`, `sub_items`
- `screenshots/` — named `<sample_id>__<system>__<step>__<timestamp>__<n>.png`
- `downloads/` — when applicable
- `linked/` — evidence from cross-system traversal (e.g., Jira tickets)
