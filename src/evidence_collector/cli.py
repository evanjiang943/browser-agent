"""CLI entrypoint for evidence-collector."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import typer

from evidence_collector.config import RunConfig, ThrottleConfig, BrowserConfig
from evidence_collector.evidence.manifest import RunManifest, write_manifest
from evidence_collector.io.paths import setup_run_dir, read_notes
from evidence_collector.io.spreadsheets import read_input, validate_columns
from evidence_collector.utils.time import now_iso

app = typer.Typer(name="evidence-collector", help="Audit evidence collection agent.")

VALID_PLAYBOOKS = (
    "tickets",
    "github-checks",
    "linkedin-enrich",
    "code-recency",
    "erp-analogue",
)

PLAYBOOK_COLUMNS: dict[str, list[str]] = {
    "tickets": ["url"],
    "github-checks": ["pr_url"],
    "linkedin-enrich": ["name"],
    "code-recency": ["repo_url", "code_string"],
    "erp-analogue": [],
}

# Playbooks with implemented runners. Values are import paths.
PLAYBOOK_RUNNERS: dict[str, str] = {
    "github-checks": "evidence_collector.runners.github_checks:GitHubChecksRunner",
    "code-recency": "evidence_collector.runners.code_recency:CodeRecencyRunner",
}


def _import_runner(import_path: str):
    """Import a runner class from a 'module:Class' string."""
    module_path, class_name = import_path.rsplit(":", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@app.command()
def run(
    playbook: str = typer.Argument(..., help="Playbook to run (tickets, github-checks, linkedin-enrich, code-recency, erp-analogue)"),
    input: str = typer.Option(..., "--input", "-i", help="Path to input CSV/XLSX file"),
    out: str = typer.Option("out", "--out", "-o", help="Output directory"),
    profile: str = typer.Option(None, "--profile", help="Browser profile to use"),
    max_per_minute: int = typer.Option(20, "--max-per-minute", help="Max pages per minute"),
    max_workers: int = typer.Option(1, "--max-workers", help="Concurrent browser sessions"),
    headless: bool = typer.Option(True, "--headless/--headful", help="Run browser headless or headful"),
    do_resume: bool = typer.Option(False, "--resume", help="Skip already-completed samples"),
) -> None:
    """Run an evidence collection playbook."""
    if playbook not in VALID_PLAYBOOKS:
        typer.echo(f"Invalid playbook '{playbook}'. Must be one of: {', '.join(VALID_PLAYBOOKS)}")
        raise typer.Exit(1)

    input_path = Path(input)
    if not input_path.exists():
        typer.echo(f"Input file not found: {input_path}")
        raise typer.Exit(1)

    config = RunConfig(
        browser=BrowserConfig(profile_dir=profile, headless=headless),
        throttle=ThrottleConfig(max_pages_per_minute=max_per_minute),
        concurrency=max_workers,
    )

    if playbook in PLAYBOOK_RUNNERS:
        # Dispatch to implemented runner — it handles setup_run_dir,
        # write_manifest, and write_results_csv internally.
        runner_cls = _import_runner(PLAYBOOK_RUNNERS[playbook])
        runner_instance = runner_cls(input_path, Path(out), config)
        typer.echo(f"playbook {playbook} starting")
        runner_instance.run()
        typer.echo(f"playbook {playbook} finished")
    else:
        # Stub path for unimplemented playbooks
        run_id = uuid.uuid4().hex[:12]
        out_path = setup_run_dir(out, playbook, run_id)
        manifest = RunManifest(
            run_id=run_id,
            playbook=playbook,
            input_file=str(input_path),
            output_dir=str(out_path),
            config=config.model_dump(),
            started_at=now_iso(),
            finished_at=None,
        )
        write_manifest(manifest, out_path)

        typer.echo(f"playbook {playbook} starting, run_id={run_id}")
        typer.echo("TODO: call playbook runner")

        manifest.finished_at = now_iso()
        write_manifest(manifest, out_path)


@app.command()
def validate(
    playbook: str = typer.Option(..., "--playbook", help="Playbook name"),
    input: str = typer.Option(..., "--input", "-i", help="Path to input CSV/XLSX file"),
) -> None:
    """Validate input file against playbook schema."""
    if playbook not in VALID_PLAYBOOKS:
        typer.echo(f"Invalid playbook '{playbook}'. Must be one of: {', '.join(VALID_PLAYBOOKS)}")
        raise typer.Exit(1)

    input_path = Path(input)
    if not input_path.exists():
        typer.echo(f"Input file not found: {input_path}")
        raise typer.Exit(1)

    required = PLAYBOOK_COLUMNS[playbook]
    rows = read_input(input_path)
    missing = validate_columns(rows, required)

    if missing:
        typer.echo(f"Missing required columns: {', '.join(missing)}")
        raise typer.Exit(1)

    columns = list(rows[0].keys()) if rows else []
    typer.echo(f"Columns: {', '.join(columns)}")
    typer.echo(f"Rows: {len(rows)}")


@app.command()
def resume(
    run_dir: str = typer.Option(..., "--run-dir", help="Path to existing run output directory"),
) -> None:
    """Resume an interrupted run."""
    run_dir_path = Path(run_dir)
    manifest_path = run_dir_path / "run_manifest.json"

    if not manifest_path.exists():
        typer.echo(f"No run_manifest.json found in {run_dir_path}")
        raise typer.Exit(1)

    manifest_data = json.loads(manifest_path.read_text())
    playbook = manifest_data["playbook"]
    run_id = manifest_data["run_id"]

    evidence_dir = run_dir_path / "evidence" / playbook
    incomplete = 0

    if evidence_dir.exists():
        for sample_dir in evidence_dir.iterdir():
            if not sample_dir.is_dir():
                continue
            notes = read_notes(sample_dir)
            if notes is None or notes.get("status") != "success":
                incomplete += 1

    typer.echo(f"Run {run_id}, playbook {playbook}: {incomplete} incomplete sample(s)")
    typer.echo("TODO: re-run incomplete samples")


if __name__ == "__main__":
    app()
