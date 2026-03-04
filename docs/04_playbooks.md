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
Generate `sample_id` deterministically:
- From primary key (ticket id / commit sha) if present
- Else hash of URL or name (stable across runs)

---

## Playbook A — Ticket screenshots + CSV extraction
### Input schema
Required columns:
- `url` (ticket URL)

Optional:
- `ticket_id` (if already known)

### Steps per sample
1. Open URL
2. Wait for ticket identifier to appear
3. Extract:
   - ticket number / id
   - assignee
   - due date
4. Screenshot:
   - top section with ticket header
   - details section with assignee/due date
   - optionally full-page tiled capture
5. Write per-sample `notes.json`

### Results schema
- `sample_id`
- `ticket_id`
- `url`
- `assignee`
- `due_date`
- `status` (success/partial/failed)
- `error` (nullable)

---

## Playbook B — GitHub checks + CI + Jira traversal
### Input schema
One of:
- `pr_url`
- `commit_url`
- `repo` + `sha`

### Steps per sample
1. Open PR/commit page
2. Screenshot PR header + description
3. Extract:
   - PR creator
   - approver(s)
   - merger (if merged)
4. Open “Checks” / CI status
   - record which checks passed / optional
   - detect merges with failing checks (note this)
5. Open CI details pages and screenshot evidence
6. Detect Jira/Linear links in PR description/commits
   - if found: open and screenshot ticket page

### Results schema
- `sample_id`
- `pr_or_commit`
- `github_url`
- `pr_creator`
- `approvers`
- `merger`
- `check_summary`
- `failed_checks_notes`
- `jira_url`
- `status`
- `error`

---

## Playbook C — CSV enrichment via LinkedIn
### Input schema
Required:
- `name`

Optional:
- `company_hint`
- `location_hint`

### Steps per sample
1. Search LinkedIn (or web) for profile
2. Pick best match (heuristics)
3. Extract:
   - linkedin_url
   - school
   - current company
   - tenure
4. Screenshot profile header (if accessible)

### Results schema
- original columns +
- `linkedin_url`, `school`, `current_company`, `tenure`, `status`, `error`

---

## Playbook D — Code recency + materiality (blame)
### Input schema
Required:
- `repo_url`
- `code_string`
- `time_window_days` (or `since_date`)

### Steps
1. Locate file containing `code_string` (GitHub search)
2. Open file
3. Switch to blame view
4. Identify last change time for the relevant lines
5. If within time window:
   - open commit
   - assess whether diff materially changes calculation behavior
   - screenshot commit diff + blame context
6. If not within window:
   - inspect downstream related code changes (within function scope)
   - if recent and potentially impactful, flag and document with screenshots

### Results schema
- `repo_url`
- `file_path`
- `snippet_hash`
- `last_change_date`
- `commit_url`
- `within_window` (bool)
- `material_change_flag` (bool)
- `rationale`
- `status`
- `error`

---

## Playbook E — ERP-analogue workflow
Because Workday isn’t available, implement a **test harness**:
- A demo web app with form + report generation + tabbed attachments

### Steps
1. Fill form with provided fields
2. Screenshot completed form
3. Submit and download report
4. Iterate tabs and download attachments
5. Save everything under run folder
