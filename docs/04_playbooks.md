# Playbooks (Implementation Specs)

## Common conventions
### Inputs
All playbooks accept:
- `--input` CSV/XLSX
- `--out` directory
- `--profile` browser profile (or persistent context dir)
- timeouts + throttling flags

### Outputs
All playbooks produce:
- `results.csv`
- `run_manifest.json`
- `run_log.jsonl`
- `evidence/<playbook>/<sample_id>/...`

### Sample IDs
Generated deterministically via `naming.py`:
- From primary key (ticket id / commit sha) if present
- Else hash of URL or name (stable across runs)

---

## Playbook A — Ticket screenshots + CSV extraction

**Status: Implemented** (`runners/tickets.py`, uses `BaseRunner` step engine)

### Input schema
Required columns:
- `url` (ticket URL)

Optional:
- `ticket_id` (if already known)

### Steps per sample
Defined as `StepDefinition` objects processed by `BaseRunner`:
1. `open_ticket` — open URL, detect login redirect / 404
2. `screenshot_ticket` — capture viewport screenshot
3. `extract_fields` — extract ticket_id, assignee, due_date via `ExtractionRule` system
4. `close_page` — cleanup

### Results schema
- `sample_id`, `ticket_id`, `url`, `assignee`, `due_date`, `status`, `error`

---

## Playbook B — GitHub checks + CI + Jira traversal

**Status: Implemented** (`runners/github_checks.py`, uses `PlaybookRunner` + `GitHubAdapter`)

Validated against real public PRs (facebook/react). See `deliverables/github-checks.md` for full auditor walkthrough.

### Input schema
One of:
- `pr_url`
- `commit_url`
- `repo` + `sha`

Loaded via `load_github_samples()` in `io/spreadsheets.py`.

### Steps per sample (7-step pipeline in `process_sample()`)
1. `open_primary_page` — open PR/commit URL; detect auth/404
2. `screenshot_pr_page` — capture PR conversation view
3. `extract_metadata` — via `GitHubAdapter.extract_pr_metadata()`:
   - title (from `bdi.js-issue-title`, `h1.gh-header-title`, or page `<title>`)
   - PR number (from URL)
   - merge status (from `.State` badge class)
   - creator (from `a.author` link)
   - approvers (from sidebar `a.assignee` links)
   - merger (from timeline text pattern)
4. `screenshot_checks` — navigate to `/checks` tab, screenshot
5. `extract_checks` — via `GitHubAdapter.extract_checks()`:
   - Check runs from `div.checks-list-item` + `.checks-list-item-name`
   - Status from SVG `aria-label` (passed/succeeded/failed)
   - Summary: `passed=N; failed=N; pending=N; optional=N`
   - `merged_with_failures` flag
6. `ci_details` — for each failed check (up to 3): follow CI details link, screenshot top + scrolled-to-logs
7. `jira_traversal` — scan PR description for Jira/Linear/GitHub issue links; screenshot first linked ticket

### Results schema
- `sample_id`, `github_url`, `pr_or_commit_id`, `pr_creator`, `approvers`, `merger`, `merge_status`, `title`, `check_summary`, `failed_checks_notes`, `jira_url`, `status`, `error`, `merged_with_failures`

---

## Playbook C — CSV enrichment via LinkedIn

**Status: Stub** (`runners/linkedin_enrich.py` — class structure only, raises `NotImplementedError`)

### Input schema
Required:
- `name`

Optional:
- `company_hint`
- `location_hint`

### Steps per sample
1. Search LinkedIn (or web) for profile
2. Pick best match (heuristics)
3. Extract: linkedin_url, school, current company, tenure
4. Screenshot profile header (if accessible)

### Results schema
- original columns + `linkedin_url`, `school`, `current_company`, `tenure`, `status`, `error`

---

## Playbook D — Code recency + materiality (blame)

**Status: Implemented** (`runners/code_recency.py`, uses `PlaybookRunner` + `GitHubAdapter`)

### Input schema
Required:
- `repo_url`
- `code_string`

Optional:
- `time_window_days` (default: 365)
- `since_date`

Loaded via `load_code_recency_samples()` in `io/spreadsheets.py`.

### Steps per sample (8-step pipeline in `process_sample()`)
1. `open_repo` — open repo URL
2. `search_code` — via `GitHubAdapter.search_code()`: find file + line range
3. `screenshot_file` — screenshot the source file with highlighted lines
4. `open_blame` — via `GitHubAdapter.open_blame_view()`
5. `extract_blame` — via `GitHubAdapter.extract_blame_dates()`: get commit dates/SHAs per line
6. `check_window` — via `is_within_window()`: determine if last change is within time window
7. `analyze_commit` — if within window, open commit, extract diff summary, assess materiality
8. `screenshot_commit` — screenshot commit diff for evidence

### Results schema
- `sample_id`, `repo_url`, `code_string`, `file_url`, `last_change_date`, `commit_url`, `within_window`, `material_change`, `materiality_rationale`, `diff_summary`, `status`, `error`

---

## Playbook E — ERP-analogue workflow

**Status: Stub** (`runners/erp_analogue.py` — class structure only, raises `NotImplementedError`)

Because Workday isn't available, this playbook would use a demo web app with form + report generation + tabbed attachments.

### Steps
1. Fill form with provided fields
2. Screenshot completed form
3. Submit and download report
4. Iterate tabs and download attachments
5. Save everything under run folder
