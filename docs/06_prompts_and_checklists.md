# Prompts & Checklists (for Claude Code + Implementation)

## A) Claude Code prompt: generate MVP skeleton
> Build a Python CLI project called `evidence_collector` using Typer.  
> Implement:  
> 1) `evidence-collector run tickets --input <csv/xlsx> --out <dir>`  
> 2) Output contract: `run_manifest.json`, `run_log.jsonl`, `results.csv`, `evidence/` folder  
> 3) Implement screenshot naming utilities and sample_id generation (deterministic).  
> 4) Add unit tests for naming + manifest writing.  
> Use Playwright for browser automation but stub selectors with TODOs.  
> Keep code modular per the scaffold.

---

## B) Claude Code prompt: implement Ticket playbook end-to-end
> Implement the `tickets` playbook using Playwright.  
> Input: CSV/XLSX column `url`.  
> For each URL: open, wait for a plausible ticket header element, take at least 2 screenshots (header + details).  
> Extract fields: `ticket_id` (best effort), `assignee` (best effort), `due_date` (best effort).  
> Always write per-sample `notes.json`.  
> Results should include status and error message.  
> Include retries and a global throttle.

---

## C) Claude Code prompt: add resumability
> Add resumability: if `notes.json` exists and status is success, skip sample.  
> If partial/failed, retry only missing steps.  
> Use `steps_completed` markers.  
> Update logs and manifest to include resume info.

---

## D) Claude Code prompt: GitHub checks + CI traversal
> Implement `github_checks` playbook.  
> Input: `pr_url` or `commit_url`.  
> Extract: PR creator, approvers, merger.  
> Screenshot: PR header, checks page, CI details page.  
> Identify checks passed/optional/failed and whether merged with fails.  
> If Jira link found, open Jira and screenshot ticket.  
> Write evidence into per-sample folder and update results.csv schema.

---

## E) Engineering checklists
### Evidence output checklist
- [ ] Every sample has its own folder
- [ ] Screenshots have consistent names
- [ ] Downloads stored under `downloads/`
- [ ] `notes.json` includes status + steps + errors
- [ ] `results.csv` has one row per sample

### Reliability checklist
- [ ] Detect login redirects early
- [ ] Configurable timeouts
- [ ] Retries with backoff on transient failures
- [ ] Rate limiting
- [ ] Error screenshots on failure

### Scale checklist
- [ ] Progress logging (sample i/N)
- [ ] Partial completion supported
- [ ] Resume works after interruption
- [ ] Optional concurrency with safe limits (2–4)

---

## F) “Material change” rubric (for code recency playbook)
A change is “material” if it could plausibly change outputs of a control-relevant computation.

Signals:
- changes to constants, thresholds, or business logic conditions
- added/removed terms in a formula
- changed rounding, timezone, currency, or unit conversions
- changed filtering criteria (included/excluded)
- changed defaults or fallback logic

Non-material examples:
- renaming variables
- formatting/comments only
- refactors with identical semantics (treat cautiously; flag if unsure)

Output should include a short rationale string auditors can read.
