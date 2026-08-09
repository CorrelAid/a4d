#!/usr/bin/env python3
"""Sanity-check a production Cloud Run Job execution against a `just backup-bq` snapshot.

Compares row counts, distinct clinic counts and schema for each WRITE_TRUNCATE'd
pipeline table against its dated snapshot, flagging gross regressions. Not a
cell-by-cell R-vs-Python comparison -- see scripts/compare_r_vs_python.py for that.

Usage:
    uv run python scripts/verify_production_run.py --backup-suffix 20260809
"""

import typer
from rich.console import Console
from rich.table import Table

from a4d.gcp.bigquery import get_bigquery_client
from a4d.gcp.verify import VERIFIED_TABLES, diff_table_stats, fetch_table_stats

console = Console()
app = typer.Typer()


@app.command()
def verify(
    backup_suffix: str = typer.Option(
        ..., "--backup-suffix", help="Date suffix `just backup-bq` used, e.g. 20260809"
    ),
) -> None:
    client = get_bigquery_client()

    before = {
        name: fetch_table_stats(client, f"{name}_{backup_suffix}") for name in VERIFIED_TABLES
    }
    after = {name: fetch_table_stats(client, name) for name in VERIFIED_TABLES}
    anomalies = diff_table_stats(before, after)

    report = Table(title="Production run verification")
    report.add_column("Table")
    report.add_column("Rows before", justify="right")
    report.add_column("Rows after", justify="right")
    report.add_column("Clinics before", justify="right")
    report.add_column("Clinics after", justify="right")
    for name in VERIFIED_TABLES:
        report.add_row(
            name,
            str(before[name].row_count),
            str(after[name].row_count),
            str(before[name].distinct_clinics),
            str(after[name].distinct_clinics),
        )
    console.print(report)

    if anomalies:
        console.print("[bold red]Anomalies found:[/bold red]")
        for anomaly in anomalies:
            console.print(f"  - {anomaly.table}: {anomaly.reason}")
        raise typer.Exit(code=1)

    console.print("[bold green]No anomalies detected.[/bold green]")


if __name__ == "__main__":
    app()
