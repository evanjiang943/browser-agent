# Claude Code Workflow — Development Guide

## 0) Setup
1. Create repo with scaffold (see `02_repo_scaffold.md`)
2. Add `docs/` with these markdown files
3. Install dependencies and Playwright browsers
4. Create `examples/` input files for each playbook

---

## 1) The development loop

For each playbook:
1. **Define the interface** (CLI + config + output schema)
2. Implement the **happy path** on 1–3 samples
3. Add evidence writing (screenshots + notes.json) and extraction
4. Scale to realistic sets (30 tickets, 60 GitHub items)
5. Harden: retries/backoff, throttling, resumability, concurrency

---

## 2) Prompt patterns that work well

### Pattern A — "Generate module with tests"
Ask for a single module plus tests for deterministic utilities.

### Pattern B — "Add feature without breaking contract"
Provide current file contents and the acceptance test (CLI invocation + expected files).

### Pattern C — "Debug with artifacts"
Paste logs + folder structure + what you saw in the browser. Ask for minimal patch + better logging.

### Pattern D — "Validate against real systems"
Run a DOM diagnostic script to discover actual selectors, fix mismatches, then run full pipeline against real pages. This is how GitHubAdapter was validated.

---

## 3) Milestones

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Output contract (manifest, logging, naming) | Done |
| 2 | Ticket playbook end-to-end | Done |
| 3 | Resumability | Done |
| 4 | GitHub checks playbook | Done (validated against live PRs) |
| 5 | Code recency playbook | Done |
| 6 | Hardening (throttle, retries, circuit breaker, concurrency) | Done |
| 7 | Runner framework refactor (BaseRunner step engine, PlaybookRunner shared orchestration) | Done |
| 8 | LinkedIn enrichment playbook | Not started |
| 9 | ERP analogue playbook | Not started |
| 10 | CLI resume command (full re-run of incomplete samples) | Not started |

---

## 4) Testing strategy

- **Unit tests** (224 passing): naming, manifest, config, CSV utils, extraction rules, text utils, retry/throttling, all three runners, GitHub adapter, step runner engine, sub-items
- **Mock HTML tests**: `examples/mock_pr.html` and `mock_pr_checks.html` test extraction against controlled DOM via real Playwright
- **Manual integration tests** (`tests/manual/`): DOM diagnostic script, real PR demo CSV. Excluded from pytest via `--ignore=tests/manual` in `pyproject.toml`
- **Deliverable walkthroughs**: `deliverables/github-checks.md` documents a full end-to-end run against real public PRs with screenshots

### Regression checklist after major changes
- [ ] `PYTHONPATH=src python -m pytest tests/ -v` — all 224 tests pass
- [ ] Tickets on 3 sample URLs
- [ ] GitHub checks on 3 real PRs
- [ ] Resume works after interruption (delete one sample's notes.json, re-run)
