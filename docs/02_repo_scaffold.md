# Repository Scaffold (Copy/Paste) — Evidence Collection Agent

## Proposed layout
```
evidence-collector/
  README.md
  pyproject.toml
  src/
    evidence_collector/
      __init__.py
      cli.py
      config.py
      runners/
        __init__.py
        base.py
        tickets.py
        github_checks.py
        linkedin_enrich.py
        code_recency.py
        erp_analogue.py
      adapters/
        __init__.py
        browser.py
        github.py
        jira_like.py
        linkedin.py
      evidence/
        __init__.py
        screenshots.py
        downloads.py
        naming.py
        manifest.py
        logging.py
      io/
        __init__.py
        spreadsheets.py
        csv_utils.py
        paths.py
      utils/
        __init__.py
        retry.py
        throttling.py
        time.py
        text.py
  tests/
    test_naming.py
    test_manifest.py
    test_spreadsheets.py
  examples/
    tickets_input.csv
    github_input.csv
    attendees.csv
  docs/
    00_project_overview_summary.md
    01_requirements_prd.md
    03_architecture.md
    04_playbooks.md
    05_claude_code_workflow.md
    06_prompts_and_checklists.md
```

## Technology recommendation (pragmatic)
- Language: **Python**
- Browser automation: **Playwright**
- Spreadsheet: `pandas` + `openpyxl`
- Logging: JSONL structured logs
- Optional: `pydantic` for config schema

## CLI entrypoints
- `evidence-collector run <playbook> --input ... --out ...`
- `evidence-collector validate --playbook ... --input ...`
- `evidence-collector resume --run-dir out/...`

## Key design rules
1. **Playbooks are pure orchestration**: they call adapters + evidence writers.
2. **Adapters encapsulate site-specific logic**: Jira vs Linear share a “ticket-like” adapter.
3. **Evidence output is a contract**: folder structure + naming is consistent.
4. **Resumability is first-class**: each sample has `notes.json` and status markers.

## Minimal “run” contract (per sample)
Each sample folder should include:
- `notes.json` with:
  - `sample_id`
  - `status` (pending/success/failed/partial)
  - `steps_completed`
  - `errors` (if any)
  - pointers to screenshots/downloads
- `screenshots/`
- `downloads/` (when applicable)
