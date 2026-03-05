# Evidence Collection Agent — PRD (Claude Code Build Guide)

> **Implementation status**: Phases 1 and 2 are complete. FR1–FR7 are implemented. Acceptance criteria met for tickets (Playbook A) and GitHub checks (Playbook B, validated against live PRs). Code recency (Playbook D) is implemented. LinkedIn (Playbook C) and ERP (Playbook E) remain as stubs. See `04_playbooks.md` for details.

## 1. Objective
Build an **Evidence Collection Agent** that automates audit evidence gathering across web-based enterprise tools using a **general browser automation core** plus optional integrations. The agent must handle **high-volume sample sets**, produce **evidence-grade artifacts**, and remain **ERP-agnostic**.

---

## 2. Target users
- **Auditors** and **audit associates** collecting evidence
- **GRC/Compliance teams** supporting audits
- **Internal control owners** asked to produce evidence quickly

---

## 3. Primary use cases (playbooks)
### 3.1 Ticket screenshots + CSV extraction
**Input:** XLSX/CSV with URLs (Linear/Jira/etc.)  
**Output:**
- `tickets.csv`: ticket_id, url, assignee, due_date, status (optional), notes
- `/evidence/tickets/<ticket_id>/screenshots/*.png`

### 3.2 GitHub commit/PR checks + CI + Jira traversal
**Input:** list of commits/PR URLs or query parameters  
**Output:**
- `github_samples.csv`: commit/pr, url, pr_creator, approver(s), merger, check_summary, failed_checks_notes, jira_url
- `/evidence/github/<sample_id>/...` (screenshots for PR, checks, CI, Jira)

### 3.3 Contact enrichment (LinkedIn)
**Input:** `attendees.csv` with names (optionally company/location)  
**Output:** same CSV with added columns: linkedin_url, school, current_company, tenure

### 3.4 Code recency + materiality (blame + commit inspection)
**Input:** code string + repo URL + time window (e.g., 365 days)  
**Output:**
- `code_review.csv`: file_path, snippet_hash, last_change_date, commit_url, within_window, material_change_flag, rationale
- Evidence screenshots of blame view + commit diff

### 3.5 ERP-like workflow (form fill → report export → attachments)
**Input:** form fields + “report tabs” list  
**Output:** report files + screenshots + downloaded attachments organized per run

---

## 4. Non-goals (initial)
- Replacing full audit workpaper tools (we output evidence; we don’t manage the audit)
- Writing to enterprise systems beyond controlled form input (keep scope to read-only + safe actions)
- Solving identity verification / SSO provisioning (assume user provides authenticated session)

---

## 5. Functional requirements
### FR1 — Input handling
- Accept CSV/XLSX for sample lists
- Validate required columns (e.g., `url`, `name`)
- Normalize identifiers (safe folder names, unique sample ids)

### FR2 — Browser automation
- Open URLs, wait for page readiness
- Handle scrolling, pagination, tab switching
- Detect common failure states (login redirect, 404, rate limiting, interstitials)

### FR3 — Screenshot capture
- Full page or tiled viewport captures depending on playbook
- Consistent naming: `<sample_id>__<step>__<timestamp>.png`
- Store per-sample evidence folder

### FR4 — Structured extraction
- Extract fields (ticket id, assignee, due date; PR metadata; etc.)
- Append to a run-level CSV with statuses per sample

### FR5 — Cross-system traversal
- If a page contains a Jira/Linear link, follow and capture evidence
- Extract and store the link in CSV

### FR6 — Robustness at scale
- Process 50–1000 samples
- Partial completion and resumability (skip completed samples)
- Configurable rate limits + backoff

### FR7 — Logging and run summaries
- Run log (timestamped events, errors)
- Summary metrics: total samples, succeeded, failed, partial, retries
- Error artifacts (e.g., screenshot of error state)

---

## 6. Non-functional requirements
- **ERP agnostic:** define system adapters; Workday is just one possible system
- **Security:** no credential exfiltration; avoid storing secrets in logs
- **Auditability:** deterministic folder structure + run manifest
- **Maintainability:** modular playbooks and system adapters

---

## 7. UX / Interface
### CLI-first (recommended for v1)
Examples:
- `agent run tickets --input tickets.xlsx --out out/ --profile chrome-default`
- `agent run github-checks --input commits.csv --out out/ --repo https://github.com/org/repo --since-days 365`
- `agent run linkedin-enrich --input attendees.csv --out out/ --max-per-minute 10`

### Configuration
- `config.yaml` for defaults (timeouts, screenshot mode, rate limits)
- Per-run overrides via CLI flags

---

## 8. Data outputs
### Required outputs for every run
- `run_manifest.json` (inputs, config, versions, timestamps)
- `run_log.jsonl` (structured logs)
- `results.csv` (playbook-specific schema)
- `evidence/` folder

### Folder structure
```
out/
  run_manifest.json
  run_log.jsonl
  results.csv
  evidence/
    <playbook>/
      <sample_id>/
        screenshots/
        downloads/
        notes.json
```

---

## 9. Quality bar / Acceptance criteria
- Can run ticket screenshots + CSV end-to-end on 30 links with 95%+ success
- Can run GitHub playbook on 60 samples with correct fields + evidence folders populated
- Can resume after interruption without duplicating work
- Output is “auditor-friendly” (clear naming, consistent structure)

---

## 10. Risks and mitigations
- **SSO / auth changes:** rely on user-managed browser profiles; detect login redirects early
- **UI variability:** use resilient selectors + fallback strategies (text-based heuristics)
- **Rate limits:** throttle + exponential backoff
- **Dynamic content:** implement wait-for-network-idle + element-ready checks

---

## 11. Phased plan
### Phase 1 (MVP) — Done
- CLI + playbook runner
- Ticket screenshots + CSV extraction
- Evidence folder + manifest/logging

### Phase 2 — Done
- GitHub checks + CI traversal (validated against real PRs)
- Resumability + concurrency (BaseRunner step engine, PlaybookRunner shared orchestration)
- Code recency + blame + materiality playbook
- Hardening: retry/throttling/circuit-breaker

### Phase 3 — Remaining
- LinkedIn enrichment playbook
- ERP analogue playbook
- JiraLike and LinkedIn adapters
