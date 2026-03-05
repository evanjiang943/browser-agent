"""CLI entrypoint for evidence-collector."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from dotenv import load_dotenv

load_dotenv()

from evidence_collector.config import RunConfig, ThrottleConfig, BrowserConfig
from evidence_collector.io.paths import read_notes

app = typer.Typer(name="evidence-collector", help="LLM-driven audit evidence collection agent.")


@app.command()
def run(
    task: str = typer.Option(None, "--task", "-t", help="Path to task description YAML/JSON file"),
    describe: str = typer.Option(None, "--describe", "-d", help="Natural language description of what to collect"),
    input: str = typer.Option(..., "--input", "-i", help="Path to input CSV/XLSX file"),
    out: str = typer.Option("out", "--out", "-o", help="Output directory"),
    profile: str = typer.Option(None, "--profile", help="Browser profile to use"),
    max_per_minute: int = typer.Option(20, "--max-per-minute", help="Max pages per minute"),
    max_workers: int = typer.Option(1, "--max-workers", help="Concurrent browser sessions"),
    headless: bool = typer.Option(True, "--headless/--headful", help="Run browser headless or headful"),
    config_file: str = typer.Option(None, "--config", help="Path to config JSON/YAML file"),
) -> None:
    """Run the evidence collection agent."""
    if not task and not describe:
        typer.echo("Either --task or --describe is required.")
        raise typer.Exit(1)

    input_path = Path(input)
    if not input_path.exists():
        typer.echo(f"Input file not found: {input_path}")
        raise typer.Exit(1)

    # Load or build config
    if config_file:
        from evidence_collector.config import load_config
        config = load_config(config_file)
    else:
        config = RunConfig()

    # Override config with CLI flags
    config.browser.profile_dir = profile
    config.browser.headless = headless
    config.throttle.max_pages_per_minute = max_per_minute
    config.concurrency = max_workers

    # Load or plan the task description
    if task:
        from evidence_collector.agent.task import load_task
        task_desc = load_task(task)
    else:
        from evidence_collector.agent.planner import plan_task
        from evidence_collector.io.spreadsheets import read_input

        typer.echo("Planning task from description...")
        rows = read_input(input_path)
        sample_row = rows[0] if rows else None
        task_desc = asyncio.run(plan_task(
            describe,
            sample_row=sample_row,
            model=config.agent.model,
            api_key_env=config.agent.api_key_env,
        ))
        typer.echo(f"Task planned: {task_desc.task_name}")
        typer.echo(f"  Goal: {task_desc.goal}")
        typer.echo(f"  Output fields: {[f.name for f in task_desc.output_schema]}")

    # Run the agent
    from evidence_collector.agent.runner import AgentRunner

    runner = AgentRunner(task_desc, input_path, Path(out), config)
    typer.echo(f"Starting agent: {task_desc.task_name}")
    runner.run()
    typer.echo(f"Agent finished: {task_desc.task_name}")


@app.command()
def validate(
    task: str = typer.Option(..., "--task", "-t", help="Path to task description YAML/JSON file"),
    input: str = typer.Option(..., "--input", "-i", help="Path to input CSV/XLSX file"),
) -> None:
    """Validate input file against task description schema."""
    from evidence_collector.agent.task import load_task
    from evidence_collector.io.spreadsheets import read_input, validate_columns

    input_path = Path(input)
    if not input_path.exists():
        typer.echo(f"Input file not found: {input_path}")
        raise typer.Exit(1)

    task_desc = load_task(task)
    rows = read_input(input_path)
    missing = validate_columns(rows, task_desc.input_columns)

    if missing:
        typer.echo(f"Missing required columns: {', '.join(missing)}")
        raise typer.Exit(1)

    columns = list(rows[0].keys()) if rows else []
    typer.echo(f"Task: {task_desc.task_name}")
    typer.echo(f"Columns: {', '.join(columns)}")
    typer.echo(f"Rows: {len(rows)}")
    typer.echo("Validation passed.")


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

    typer.echo(f"Run {run_id}, task {playbook}: {incomplete} incomplete sample(s)")
    typer.echo("TODO: re-run incomplete samples")


if __name__ == "__main__":
    app()
