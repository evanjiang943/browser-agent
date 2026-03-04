# Claude Code Workflow — How to Build This Project Fast

## 0) One-time setup
1. Create a new repo with the scaffold in `02_repo_scaffold.md`
2. Add `docs/` and drop these markdown files there
3. Install dependencies and Playwright browsers
4. Create `examples/` input CSVs for each playbook

---

## 1) The tight development loop
For each playbook:
1. **Define the interface** (CLI + config + output schema)
2. Implement the **happy path** on 1–3 samples
3. Add evidence writing (screenshots + notes.json) and extraction
4. Scale to realistic sets (30 tickets, 60 github items)
5. Harden: retries/backoff, throttling, resumability, concurrency

---

## 2) Prompt patterns that work well with Claude Code
### Pattern A — “Generate module with tests”
Ask for a single module plus tests for deterministic utilities.

### Pattern B — “Add feature without breaking contract”
Provide current file contents and the acceptance test (CLI invocation + expected files).

### Pattern C — “Debug with artifacts”
Paste logs + folder structure + what you saw in the browser. Ask for minimal patch + better logging.

---

## 3) Milestones (recommended)
1. Output contract (manifest/logging/naming)
2. Ticket playbook end-to-end
3. Resumability
4. GitHub playbook
5. Hardening (throttle/retries/concurrency)
6. Additional playbooks (LinkedIn, blame, ERP analogue)

---

## 4) Testing strategy
- Unit tests for naming/hashing/manifest
- Integration runs using `examples/` small datasets
- Regression checklist after major changes:
  - tickets on 3 samples
  - schema intact
  - resume works
