# Evidence Collection

An LLM-driven browser agent that automates audit evidence gathering from the web.

## What It Does

You give it a spreadsheet of items to check and describe what evidence to collect. The agent autonomously navigates web pages, extracts data, takes screenshots, and produces a structured evidence package — ready for an auditor to review.

**Example:** Given a list of GitHub PR URLs, it can open each PR, read the title and author, check merge status, capture CI results, screenshot the page, and compile everything into a results CSV with an annotated markdown report.

## How It Works

1. **Describe the task** — Upload a CSV/XLSX and describe what to collect in natural language, or provide a YAML task file
2. **Review the plan** — The agent proposes a structured task (output fields, instructions, constraints) for your approval
3. **Agent runs** — For each row in your spreadsheet, Claude navigates pages using 15 browser tools (open URLs, click, scroll, read text, take screenshots, record fields)
4. **Get results** — Download a zip containing:
   - `results.csv` — extracted data for all samples
   - `report.md` — visual walkthrough with screenshots showing what the agent did
   - Per-sample evidence (screenshots, downloads, full tool call traces)

## Interfaces

**Web UI** — Chat-based interface at `localhost:8000`. Upload a file, describe what you need, approve the task, watch progress in real time.

```bash
evidence-web
```

**CLI** — For scripted/batch use.

```bash
evidence-collector run --task examples/tasks/github-checks.yaml --input examples/github_checks.csv --out results/
evidence-collector run --describe "For each URL, find the company name and founding year" --input companies.csv --out results/
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent brain | Claude (Anthropic API) via tool calling |
| Browser automation | Playwright (Chromium) |
| Web UI | FastAPI + WebSocket + single-file HTML/CSS/JS |
| CLI | Typer |
| Data models | Pydantic v2 |
| Input parsing | pandas + openpyxl |

## Architecture

```
src/evidence_collector/
├── agent/          # LLM agent: task models, 15 browser tools, agent loop, runner, prompts, audit, report
├── adapters/       # Browser adapter (Playwright wrapper)
├── evidence/       # Naming, manifest/notes models, structured logging
├── io/             # Path setup, spreadsheet reading, CSV output
├── utils/          # Retry, throttling, circuit breaker, text parsing, time
├── web/            # FastAPI app, WebSocket handler, chat planner, session, progress
└── cli.py          # CLI entrypoint
```

The agent loop is the core: for each sample, it sends the task description and sample data to Claude with 15 available tools. Claude decides what to navigate, read, click, and extract. Every tool call is recorded in `agent_trace.jsonl` for full auditability. After completion, a markdown report is generated with inline screenshots showing exactly what the agent saw and did.

## Key Design Decisions

- **No hardcoded logic** — The agent figures out navigation and extraction at runtime. No CSS selectors, no domain-specific adapters.
- **Auditability first** — Every action is traced. `verify_trace()` checks that recorded values actually appeared in page text the agent observed.
- **Crash-safe** — Atomic writes for all state files. Per-sample `notes.json` enables resumability on restart.
- **Schema enforcement** — `record_field` rejects unknown field names. Post-loop validation flags missing required fields.
