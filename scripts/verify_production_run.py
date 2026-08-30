#!/usr/bin/env python3
"""Sanity-check a production Cloud Run Job execution against a `just backup-bq` snapshot.

Compares row counts, distinct clinic counts and schema for each WRITE_TRUNCATE'd
pipeline table against its dated snapshot, flagging gross regressions. Not a
cell-by-cell R-vs-Python comparison -- see scripts/compare_outputs.py for that.

Usage:
    uv run python scripts/verify_production_run.py --backup-suffix 20260809
"""

import typer
from rich.console import Console
from rich.table import Table

from a4d.gcp.bigquery import get_bigquery_client
from a4d.gcp.verify import VERIFIED_TABLES, diff_table_stats, fetch_table_stats_if_present

console = Console()
app = typer.Typer()


@app.command()
def verify(
    backup_suffix: str = typer.Option(
        ..., "--backup-suffix", help="Date suffix `just backup-bq` used, e.g. 20260809"
    ),
) -> None:
    client = get_bigquery_client()

    # A table with no snapshot is one published for the first time, not a
    # failure -- it is reported as new and excluded from the before/after diff,
    # which has nothing to compare it against.
    before = {}
    for name in VERIFIED_TABLES:
        stats = fetch_table_stats_if_present(client, f"{name}_{backup_suffix}")
        if stats is not None:
            before[name] = stats
    after = {}
    for name in VERIFIED_TABLES:
        stats = fetch_table_stats_if_present(client, name)
        if stats is not None:
            after[name] = stats
    anomalies = diff_table_stats(before, after)
    new_tables = sorted(set(after) - set(before))
    vanished = sorted(set(VERIFIED_TABLES) - set(after))

    report = Table(title="Production run verification")
    report.add_column("Table")
    report.add_column("Rows before", justify="right")
    report.add_column("Rows after", justify="right")
    report.add_column("Clinics before", justify="right")
    report.add_column("Clinics after", justify="right")
    for name in VERIFIED_TABLES:
        before_stats = before.get(name)
        after_stats = after.get(name)
        report.add_row(
            name,
            "-" if before_stats is None else str(before_stats.row_count),
            "-" if after_stats is None else str(after_stats.row_count),
            "-" if before_stats is None else str(before_stats.distinct_clinics),
            "-" if after_stats is None else str(after_stats.distinct_clinics),
        )
    console.print(report)

    if new_tables:
        console.print(
            f"[cyan]Published for the first time (no snapshot to compare): "
            f"{', '.join(new_tables)}[/cyan]"
        )

    if vanished:
        console.print("[bold red]Expected but absent after the run:[/bold red]")
        for name in vanished:
            console.print(f"  - {name}")

    if anomalies:
        console.print("[bold red]Anomalies found:[/bold red]")
        for anomaly in anomalies:
            console.print(f"  - {anomaly.table}: {anomaly.reason}")

    if anomalies or vanished:
        raise typer.Exit(code=1)

    console.print("[bold green]No anomalies detected.[/bold green]")


if __name__ == "__main__":
    app()
