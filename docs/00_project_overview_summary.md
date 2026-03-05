# Evidence Collection — Detailed Summary (Auditor + Browser Agent)

> **Implementation status**: Core framework complete. Playbooks A (Tickets), B (GitHub Checks), and D (Code Recency) are fully implemented with 224 tests passing. GitHub Checks validated against real public PRs. Playbooks C (LinkedIn) and E (ERP) are stubs. See `03_architecture.md` for the actual architecture and `04_playbooks.md` for per-playbook details.

## What this project is
Auditors often need to collect evidence from many internal systems (e.g., Workday, GitHub, NetSuite, Jira/Linear) using **read-only access**. Evidence collection becomes the bottleneck because it is:
- **High-volume** (dozens to thousands of “samples”)
- **UI-driven** (clicking, filtering, opening links, downloading artifacts, taking screenshots)
- **Cross-system** (a single sample may require traversing GitHub → CI → Jira → exported report)
- **Strictly documented** (screenshots, CSVs, and file bundles must support audit workpapers)

The goal is to build a **General Browser Agent** that can reliably execute evidence-collection playbooks, with **ERP-agnostic** design (no Workday dependency) and optional integrations when available.

---

## Core user problem
Auditors need to prove things like “this control operated,” “this change was reviewed,” or “these users have the right attributes.” The supporting artifacts are typically:
- Screenshots (often full viewport coverage, including metadata and timestamps)
- CSV/Excel output tying samples to the collected evidence
- Downloaded attachments or exported reports
- Notes/flags for exceptions (e.g., failed checks merged anyway)

Today, auditors do this manually (hours/days). The agent should do it in a reproducible, logged, evidence-safe way.

---

## Key capabilities implied
### 1) Navigate and collect at scale
- Process **lists of links** (e.g., 30 Linear ticket URLs; 60 GitHub commits; 50–1000 users).
- Execute consistent steps per sample, with retries and partial success handling.

### 2) Evidence-grade screenshots
- Capture screenshots with repeatable conventions:
  - Full-viewport tiling/scroll capture when needed
  - Clear labeling (sample id, timestamp, source system)
  - Saved into a folder structure auditors can use

### 3) Structured extraction into CSV
- While collecting screenshots, extract key fields into a table:
  - Ticket #: assignee, due date
  - Commit: PR creator/approver/merger, check outcomes, Jira link
  - Contact enrichment: LinkedIn URL, school, current company, tenure

### 4) Cross-link traversal
- If a GitHub commit links to Jira, follow it and capture evidence there.
- If CI checks exist, open them and capture relevant evidence.

### 5) Change-history reasoning (Git blame / commit inspection)
- Given a code string:
  - Locate file
  - Use blame view to find last modifying commit/date for that snippet
  - Determine if changes within a time window (e.g., 1 year)
  - If within window, inspect commit to judge “material” impact
  - Also detect downstream code changes that could affect the function, even if the snippet itself wasn’t changed

### 6) Form fill + export workflow (ERP analog)
- Fill form fields, capture screenshot of completed form
- Download resulting report
- Iterate tabs, download attachments
- Since Workday isn’t available, create an analogous, testable workflow with a public or mock app.

---

## Example playbooks (from your spec)
### A) Ticket screenshots + CSV compilation
**Input:** Excel list of Linear ticket URLs  
**Task:** For each ticket:
1. Open URL
2. Take screenshot
3. Extract: ticket number, assignee, due date
4. Output CSV + screenshot bundle

### B) GitHub evidence harvesting (high volume, multi-hop)
**Input:** set of ~60 commits (or PRs)  
**Task:** For each commit/PR:
1. Capture screenshots of each viewport section (tiling/scroll)
2. Open checks; identify which pass / optional
3. Identify merges where checks failed
4. Open CI logs; screenshot them
5. If Jira link exists, open Jira; take screenshots

**Outputs:**
- CSV with: commit id, link, PR creator, approver, merger, notes on failures, Jira link
- File directory: folder per sample; screenshots stored inside

### C) CSV enrichment via LinkedIn
**Input:** CSV of names  
**Task:** For each:
1. Find LinkedIn profile
2. Extract & append: LinkedIn URL, school, most recent employer, tenure

### D) Code snippet recency + materiality
**Input:** code string and time window (e.g., within the last year)  
**Task:**
1. Find file
2. Switch to blame view
3. Determine last change time for snippet
4. If within window → open commit, assess material impact, screenshot
5. If snippet older but related downstream changes are recent → assess potential impact, screenshot

### E) ERP-like form/report workflow
**Input:** form inputs  
**Task:** Fill form → screenshot → download report → download attachments across tabs  
**Note:** Use an ERP-agnostic analogue for testing.

---

## Constraints and design implications
- **ERP agnostic:** assume Workday is not available; build interfaces adaptable to any ERP or HRIS.
- **Sometimes no integration:** agent must work in fully manual UI navigation mode.
- **But also support integrations:** if APIs exist, use them to reduce UI work.
- **Complex tasks require filesystem orchestration + subagents:** scale and robustness suggests:
  - A job queue per sample
  - Separate “collector” subagents for each system or step
  - A shared filesystem structure as the contract between subagents

---

## What “done” looks like (high-level)
A user can provide an input file (CSV/XLSX), a time window, and credentials/session (or a browser profile), choose a playbook, and the system produces:
- A structured CSV of extracted metadata
- A folder of evidence screenshots/attachments organized by sample
- A run log and summary of failures/exceptions
- Repeatable execution (same inputs → same outputs format)
