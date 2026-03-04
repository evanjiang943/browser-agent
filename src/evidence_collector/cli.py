"""CLI entrypoint for evidence-collector."""

import typer

app = typer.Typer(name="evidence-collector", help="Audit evidence collection agent.")


@app.command()
def run(
    playbook: str = typer.Argument(..., help="Playbook to run (tickets, github-checks, linkedin-enrich, code-recency, erp-analogue)"),
    input: str = typer.Option(..., "--input", "-i", help="Path to input CSV/XLSX file"),
    out: str = typer.Option("out", "--out", "-o", help="Output directory"),
    profile: str = typer.Option(None, "--profile", help="Browser profile to use"),
) -> None:
    """Run an evidence collection playbook."""
    # TODO: resolve playbook by name, load config, invoke runner
    raise NotImplementedError("run command not yet implemented")


@app.command()
def validate(
    playbook: str = typer.Option(..., "--playbook", help="Playbook name"),
    input: str = typer.Option(..., "--input", "-i", help="Path to input CSV/XLSX file"),
) -> None:
    """Validate input file against playbook schema."""
    # TODO: load playbook schema, validate input columns
    raise NotImplementedError("validate command not yet implemented")


@app.command()
def resume(
    run_dir: str = typer.Option(..., "--run-dir", help="Path to existing run output directory"),
) -> None:
    """Resume an interrupted run."""
    # TODO: load run manifest, identify incomplete samples, resume runner
    raise NotImplementedError("resume command not yet implemented")


if __name__ == "__main__":
    app()
