# Evidence Collection — Documentation Index

## Project Status

Three of five playbooks are fully implemented and tested (224 tests passing). The core framework (runner engine, browser adapter, evidence output, config, CLI) is complete. GitHub Checks has been validated against real public PRs with a full auditor walkthrough.

### What's Built

| Component | Status |
|-----------|--------|
| Foundation (naming, manifest, logging, config, I/O, utils) | Done |
| Runner framework (BaseRunner, PlaybookRunner, step engine) | Done |
| BrowserAdapter (Playwright, screenshots, login/404 detection) | Done |
| Playbook A — Tickets | Done |
| Playbook B — GitHub Checks + CI + Jira traversal | Done (validated against live GitHub) |
| Playbook D — Code Recency + blame + materiality | Done |
| GitHubAdapter (metadata, checks, blame, code search) | Done |
| CLI (run, validate) | Done |
| Playbook C — LinkedIn Enrich | Stub |
| Playbook E — ERP Analogue | Stub |
| JiraLikeAdapter, LinkedInAdapter | Stubs |
| CLI resume command | Stub |

## Documentation Files

| File | Purpose |
|------|---------|
| `00_project_overview_summary.md` | High-level problem statement, capabilities, and playbook descriptions |
| `01_requirements_prd.md` | PRD with functional/non-functional requirements and acceptance criteria |
| `02_repo_scaffold.md` | Actual repository layout and module descriptions |
| `03_architecture.md` | Architecture: runner framework, adapters, extraction, evidence output |
| `04_playbooks.md` | Per-playbook specs with implementation status |
| `05_claude_code_workflow.md` | Development workflow and milestone tracking |
| `06_prompts_and_checklists.md` | Implementation prompts and engineering checklists |

## Deliverables

| File | Description |
|------|-------------|
| `deliverables/github-checks.md` | Full auditor walkthrough for GitHub Checks with screenshots and real output |

## Where to Go Next

The remaining work is Playbooks C (LinkedIn) and E (ERP), plus their adapters. The framework is ready — new playbooks only need to implement `playbook_name`, `result_columns`, `load_samples()`, `process_sample()`, and `create_adapters()` on `PlaybookRunner`.
