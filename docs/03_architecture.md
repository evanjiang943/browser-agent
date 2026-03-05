# Architecture — Evidence Collection Agent

## 1) Overview

A **playbook runner** processes *many samples* from an input spreadsheet and produces *auditor-grade evidence artifacts*: screenshots, extracted data CSVs, and per-sample audit trails.

### Component layers

```
CLI (cli.py)
  └─ Runner (runners/base.py)
       ├─ BrowserAdapter (adapters/browser.py)  — generic Playwright wrapper
       ├─ System Adapters (github.py, etc.)     — site-specific extraction
       ├─ Evidence Writer (evidence/, io/)       — naming, notes, manifest, CSV
       └─ Utils (retry, throttling, time, text)  — cross-cutting concerns
```

---

## 2) Runner framework

Two base classes handle all orchestration. Playbook authors only define sample processing logic.

### BaseRunner — generic step engine

`BaseRunner` executes a list of `StepDefinition` objects against each sample, with:

- **StepDefinition**: `name`, `fn` (async callable taking `SampleContext`), `required` (bool), `max_retries`
- **SampleContext**: mutable context threaded through steps — provides `screenshot()`, `save_file()`, `record()`, `fail()`, `sub_item()`, `flush_notes()`
- **SubItemContext**: nested context for processing items within a sample (e.g., individual CI checks)
- **Resumability**: checks `steps_completed` in `notes.json` and skips already-done steps
- **Error handling**: required step failure aborts the sample; optional step failure marks it partial

Used by: `TicketsRunner` (Playbook A)

### PlaybookRunner — shared orchestration

`PlaybookRunner` provides shared `_run_async()` that handles config initialization, browser lifecycle, throttling, circuit breaking, results CSV writing, and manifest creation. Subclasses implement:

- `playbook_name` (property) — e.g., `"github-checks"`
- `result_columns` (property) — CSV column list
- `load_samples()` — parse input spreadsheet into sample dicts
- `process_sample(sample)` — async method that does the actual work, returns a result dict
- `create_adapters(config, browser_adapter)` — initialize any system-specific adapters

Used by: `GitHubChecksRunner` (Playbook B), `CodeRecencyRunner` (Playbook D)

---

## 3) Adapters

### BrowserAdapter (`adapters/browser.py`)

Generic Playwright Chromium wrapper:

- `open(url)` — navigate with `networkidle` wait; detects login redirects (`LoginRedirectError`) and 404s (`PageNotFoundError`)
- `screenshot(page, path, mode)` — viewport or tiled capture
- `download_file(page, selector, path)` — trigger and save downloads
- `close()` — cleanup browser resources
- Lazy browser initialization via `_ensure_browser()`
- Error screenshots captured automatically on navigation failures

Also provides a declarative extraction system:
- `ExtractionRule` — dataclass with `field`, `selectors`, `fallback_pattern`, `transform`, `required`
- `extract_fields(page, rules)` — evaluate rules against a page, returning a dict
- `find_links_matching(page, patterns)` — find deduplicated hrefs matching regex patterns
- `verify_url(url)` — HEAD/GET check for URL reachability

### GitHubAdapter (`adapters/github.py`)

GitHub-specific browser interactions, validated against real GitHub DOM:

- **Navigation**: `open_pr()`, `open_commit()`, `open_checks()`, `open_blame_view()`, `search_code()`
- **Extraction**: `extract_pr_metadata()` (title, PR number, merge status, creator, approvers, merger), `extract_checks()` (check names, pass/fail/pending from SVG aria-labels), `extract_blame_dates()`, `extract_commit_diff_summary()`, `find_ticket_links()`
- **CI traversal**: `get_ci_details_url()` — find the external CI link for a named check

Multi-strategy extraction pattern: each field tries primary CSS selector, then fallback selectors, then text/regex heuristics. This provides resilience against GitHub DOM changes.

### Stub adapters

- `JiraLikeAdapter` — ticket system interactions (not yet implemented)
- `LinkedInAdapter` — profile search and extraction (not yet implemented)

---

## 4) Evidence output

### Per-run outputs

| File | Purpose |
|------|---------|
| `run_manifest.json` | Run metadata: ID, playbook, config, timestamps |
| `run_log.jsonl` | Timestamped event stream (sample_start, sample_end, errors) |
| `results.csv` | One row per sample with all extracted data |

### Per-sample outputs

```
evidence/<playbook>/<sample_id>/
  notes.json          # SampleNotes: status, steps_completed, errors, screenshots, downloads, sub_items
  screenshots/        # Named: <sample_id>__<system>__<step>__<timestamp>__<n>.png
  downloads/          # Downloaded files
  linked/             # Evidence from cross-system traversal
```

### Key patterns

- **Atomic writes**: `write_manifest()` and `write_notes()` use `tempfile.NamedTemporaryFile` + `os.replace()` for crash safety
- **Deterministic sample IDs**: `generate_sample_id()` derives from primary_key > URL > name (stable across runs)
- **Pydantic models**: `RunManifest`, `SampleNotes`, `SubItemNotes`, all config models use Pydantic v2 for validation and serialization

---

## 5) Resumability

Each sample is an independent unit tracked by `notes.json`:

1. Before processing a sample, the runner checks `notes.json` — if `status == "success"`, skip
2. Each step writes its completion marker to `steps_completed` immediately via `flush_notes()`
3. On rerun, completed steps within a sample are skipped; only pending/failed steps retry
4. Sub-items (e.g., individual CI checks) also track their own completion state

This means: interrupted runs can be resumed by re-running the same command. No work is duplicated.

---

## 6) Extraction strategy

Three-layer approach, used consistently across adapters:

1. **CSS selectors** — precise DOM queries (e.g., `bdi.js-issue-title`, `.State--merged`)
2. **Text heuristics** — regex against `page.inner_text("body")` (e.g., `(\w+)\s+merged\s+commit`)
3. **Page metadata** — `page.title()`, URL parsing, element attributes (e.g., SVG `aria-label`)

If all strategies fail for a non-required field, the result is empty string (not an error). For required fields, a warning is logged and the sample continues with best-effort data.

---

## 7) Rate limiting and resilience

- **Throttle**: sliding-window rate limiter (`max_pages_per_minute`, default 20)
- **Retry**: exponential backoff on transient failures (`retry_async`, configurable attempts)
- **Circuit breaker**: pauses all processing if too many consecutive failures (prevents hammering a down service)
- **Concurrency**: `asyncio.Semaphore` limits parallel browser sessions (default 1, configurable)

---

## 8) Security and privacy

- No page HTML stored in logs
- No session cookies stored unless user opts in via `--profile`
- Tokens redacted from log output
- Read-only mode: the agent only navigates and screenshots, never modifies remote state
