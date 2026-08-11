#!/usr/bin/env python3
"""Diff a Python pipeline output directory against the frozen R baseline.

Migration-only tooling with a defined end-of-life (R's retirement, ticket 12)
-- deliberately not wired into `a4d.cli`. Decoupled from pipeline execution:
takes two existing output directories and diffs them. Logic lives in
`a4d.migration.compare`; this is a thin CLI + HTML report writer.

Usage:
    uv run python scripts/compare_outputs.py \
        --r-dir "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r" \
        --py-dir "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python" \
        --report-out compare_report.html
"""

from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from rich.console import Console
from rich.table import Table

from a4d.migration.compare import (
    PRODUCT_ENTRY_DATE_CLASSIFIERS,
    DirectoryComparison,
    compare_directory,
    render_html_report,
)

console = Console()
app = typer.Typer()

PATIENT_KEY_COLS = ["patient_id", "sheet_name"]
PRODUCT_KEY_COLS = ["clinic_id", "product", "product_sheet_name", "product_entry_date"]

CLASSIFIERS_BY_COLUMN = {"product_entry_date": PRODUCT_ENTRY_DATE_CLASSIFIERS}


def _load_parquet_dir(directory: Path) -> dict[str, pl.DataFrame]:
    return {path.name: pl.read_parquet(path) for path in sorted(directory.glob("*.parquet"))}


def _numeric_cols(frames: dict[str, pl.DataFrame]) -> list[str]:
    if not frames:
        return []
    sample = next(iter(frames.values()))
    return [name for name, dtype in sample.schema.items() if dtype.is_numeric()]


def _compare_arm(r_dir: Path, py_dir: Path, key_cols: list[str]) -> DirectoryComparison:
    r_frames = _load_parquet_dir(r_dir)
    py_frames = _load_parquet_dir(py_dir)
    numeric_cols = _numeric_cols(r_frames)
    return compare_directory(r_frames, py_frames, key_cols=key_cols, numeric_cols=numeric_cols)


def _print_summary(arm: str, comparison: DirectoryComparison) -> None:
    table = Table(title=f"{arm} — file-level summary")
    table.add_column("File")
    table.add_column("Shape match")
    table.add_column("Totals mismatches", justify="right")
    table.add_column("Column diffs", justify="right")
    table.add_column("Cell mismatches", justify="right")

    for file_comparison in comparison.files:
        column_diffs = (
            len(file_comparison.columns.only_in_r)
            + len(file_comparison.columns.only_in_py)
            + len(file_comparison.columns.dtype_mismatches)
        )
        table.add_row(
            file_comparison.file_name,
            "✓" if file_comparison.shape.match else "✗",
            str(len(file_comparison.totals)),
            str(column_diffs),
            str(len(file_comparison.cell_mismatches)),
        )
    console.print(table)

    if comparison.only_in_r:
        console.print(
            f"[yellow]Only in R ({len(comparison.only_in_r)}):[/yellow] "
            f"{', '.join(comparison.only_in_r)}"
        )
    if comparison.only_in_py:
        console.print(
            f"[yellow]Only in Python ({len(comparison.only_in_py)}):[/yellow] "
            f"{', '.join(comparison.only_in_py)}"
        )


@app.command()
def compare(
    r_dir: Annotated[Path, typer.Option("--r-dir", help="Root of the frozen R output directory")],
    py_dir: Annotated[Path, typer.Option("--py-dir", help="Root of the Python output directory")],
    report_out: Annotated[
        Path, typer.Option("--report-out", help="Where to write the HTML report")
    ] = Path("compare_report.html"),
) -> None:
    patient_comparison = _compare_arm(
        r_dir / "patient_data_cleaned", py_dir / "patient_data_cleaned", PATIENT_KEY_COLS
    )
    product_comparison = _compare_arm(
        r_dir / "product_data_cleaned", py_dir / "product_data_cleaned", PRODUCT_KEY_COLS
    )

    _print_summary("Patient", patient_comparison)
    _print_summary("Product", product_comparison)

    combined = DirectoryComparison(
        files=patient_comparison.files + product_comparison.files,
        only_in_r=patient_comparison.only_in_r + product_comparison.only_in_r,
        only_in_py=patient_comparison.only_in_py + product_comparison.only_in_py,
    )
    html = render_html_report(combined, classifiers_by_column=CLASSIFIERS_BY_COLUMN)
    report_out.write_text(html)
    console.print(f"[bold green]Report written to {report_out}[/bold green]")


if __name__ == "__main__":
    app()
