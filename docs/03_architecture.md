# Architecture — General Browser Agent for Evidence Collection

## 1) Mental model
You are building a **playbook runner** that processes *many samples* and produces *auditor-grade evidence artifacts*.

### Key components
- **Runner**: orchestrates a playbook, loads inputs, manages concurrency/resume
- **Browser adapter**: opens pages, clicks, waits, screenshots, downloads
- **System adapters**: GitHub/Jira/Linear/LinkedIn/etc. built on top of browser adapter
- **Evidence writer**: naming + folder layout + manifest + CSV output
- **Log + audit trail**: JSONL logs, per-sample notes, run manifest

---

## 2) Dataflow
1. Input ingestion (CSV/XLSX) → normalized samples list
2. For each sample:
   - execute steps (idempotent)
   - write screenshots + downloads
   - extract structured fields
   - append to results dataset
3. At end:
   - write `results.csv`
   - write summary report + manifest

---

## 3) Resumability design
Each sample is an independent unit:
- A **sample status file** determines whether to skip.
- Each step writes its own completion marker.
- On rerun, skip completed steps; retry failed steps.

Practical implementation:
- `notes.json` includes `steps_completed` array
- Each step checks `if step in steps_completed: return`
- Use atomic file writes for markers

---

## 4) Subagents / workers concept (works well with Claude Code)
Even if you implement in one process, **design like** you have subagents:
- `tickets_worker(sample)`  
- `github_worker(sample)`  
- `jira_worker(sample)`  
- `ci_worker(sample)`  

This makes it easy to:
- parallelize later
- isolate system-specific failures
- test locally

---

## 5) Screenshot strategy
### Screenshot modes
- **Viewport**: quick capture of current view
- **Tiled/scroll**: for long pages; capture each scroll segment
- **Full page**: when supported and stable

### Naming convention
```
<sample_id>__<system>__<step>__<YYYYMMDD-HHMMSS>__<n>.png
```

### “Evidence-grade” rules
- Capture headers that include identifiers (ticket id / PR id)
- Capture timestamps when possible
- Capture error states explicitly (login page, access denied)

---

## 6) Extraction strategy
Use layered extraction:
1. Structured selectors (preferred)
2. Text heuristics fallback (regex on visible text)
3. Manual review markers if extraction fails (status=partial)

---

## 7) Rate limiting + backoff
You want:
- global throttle (max pages/min)
- per-sample retry with exponential backoff
- circuit breaker (pause if too many auth failures)

---

## 8) Security and privacy
- Don’t log page HTML.
- Don’t store session cookies unless user explicitly opts in.
- Redact tokens from logs.
- Keep a “safe mode” that only reads + screenshots.

---

## 9) Extensibility: adapter interface
Define a simple adapter contract:
- `open_sample(sample)`
- `extract_fields(sample) -> dict`
- `collect_evidence(sample) -> list[Artifact]`

This allows adding new systems (NetSuite, ServiceNow) later.
