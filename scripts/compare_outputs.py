#!/usr/bin/env python3
"""Diff a Python pipeline output directory against the frozen R baseline.

Migration-only tooling with a defined end-of-life (R's retirement, ticket 12)
-- deliberately not wired into `a4d.cli`. Decoupled from pipeline execution:
takes two existing output directories and diffs them. Logic lives in
`a4d.migration.compare`; this is a thin CLI + report writer. Per stage
(patient/product x raw/cleaned) writes one Excel workbook -- summary sheets
(aggregate counts) plus the actual flagged rows, one sheet per measure. Excel,
not HTML, because triage means loading this as a dataframe, filtering,
sorting, and adding columns -- not just reading a static page.

Usage:
    uv run python scripts/compare_outputs.py \
        --r-dir "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r" \
        --py-dir "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python" \
        --report-out compare_report.xlsx
"""

import re
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from openpyxl import Workbook
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from a4d.migration.compare import (
    PRODUCT_ENTRY_DATE_CLASSIFIERS,
    DirectoryComparison,
    FileComparison,
    build_mismatch_rows,
    build_summary_rows,
    compare_directory,
)

console = Console()
app = typer.Typer()

PATIENT_KEY_COLS = ["patient_id", "sheet_name"]
PATIENT_ID_COL = "patient_id"
# Fields with allowed-value validation in reference_data/data_cleaning.yaml --
# the genuinely categorical patient columns, not free text.
PATIENT_CATEGORICAL_COLS = [
    "analog_insulin_long_acting",
    "analog_insulin_rapid_acting",
    "clinic_visit",
    "complication_screening_eye_exam_value",
    "complication_screening_foot_exam_value",
    "dm_complication_eye",
    "dm_complication_kidney",
    "dm_complication_others",
    "hospitalisation_cause",
    "human_insulin_intermediate_acting",
    "human_insulin_pre_mixed",
    "human_insulin_short_acting",
    "insulin_regimen",
    "insulin_type",
    "insulin_subtype",
    "observations_category",
    "patient_consent",
    "province",
    "remote_followup",
    "status",
    "support_level",
]

PRODUCT_KEY_COLS = ["clinic_id", "product", "product_sheet_name", "product_entry_date"]
# product_entry_date is unreliable as an identity anchor (see ticket 17) -- "product"
# (the product name) is the natural identity check here instead.
PRODUCT_ID_COL = "product"
PRODUCT_CATEGORICAL_COLS = ["product_category", "product_balance_status"]

CLASSIFIERS_BY_COLUMN = {"product_entry_date": PRODUCT_ENTRY_DATE_CLASSIFIERS}

# (label, output subdir, row-alignment key, identity column, categorical columns).
# Raw and cleaned are compared separately so a divergence can be localized to
# extraction vs. cleaning; categorical columns listed here that don't exist yet
# at the raw stage are silently skipped by compare_categorical_overlap.
STAGES = [
    (
        "Patient (raw)",
        "patient_data_raw",
        PATIENT_KEY_COLS,
        PATIENT_ID_COL,
        PATIENT_CATEGORICAL_COLS,
    ),
    (
        "Patient (cleaned)",
        "patient_data_cleaned",
        PATIENT_KEY_COLS,
        PATIENT_ID_COL,
        PATIENT_CATEGORICAL_COLS,
    ),
    (
        "Product (raw)",
        "product_data_raw",
        PRODUCT_KEY_COLS,
        PRODUCT_ID_COL,
        PRODUCT_CATEGORICAL_COLS,
    ),
    (
        "Product (cleaned)",
        "product_data_cleaned",
        PRODUCT_KEY_COLS,
        PRODUCT_ID_COL,
        PRODUCT_CATEGORICAL_COLS,
    ),
]


def _load_parquet_dir(directory: Path) -> dict[str, pl.DataFrame]:
    return {path.name: pl.read_parquet(path) for path in sorted(directory.glob("*.parquet"))}


def _numeric_cols(frames: dict[str, pl.DataFrame]) -> list[str]:
    if not frames:
        return []
    sample = next(iter(frames.values()))
    return [name for name, dtype in sample.schema.items() if dtype.is_numeric()]


def _compare_arm(
    r_dir: Path, py_dir: Path, key_cols: list[str], id_col: str, categorical_cols: list[str]
) -> DirectoryComparison:
    r_frames = _load_parquet_dir(r_dir)
    py_frames = _load_parquet_dir(py_dir)
    numeric_cols = _numeric_cols(r_frames)
    # compare_directory/compare_categorical_overlap skip a column not present on
    # both sides of a given file -- raw output isn't schema-normalized like cleaned
    # output, so which columns exist can vary file by file, not just by directory.
    return compare_directory(
        r_frames,
        py_frames,
        key_cols=key_cols,
        numeric_cols=numeric_cols,
        id_col=id_col,
        categorical_cols=categorical_cols,
    )


LEGEND = """\
[bold]Shape match[/bold]        -- do R and Python have the same row count for this file? A \
coarse structural check: matching shape says nothing about whether individual cell values agree.

[bold]ID divergence[/bold]      -- identities (patient_id for patient, product name for \
product) present on only one side, regardless of row count. Independent of the row-alignment \
key used for row-key/cell divergence below -- catches a patient or product dropped entirely, \
even when that key is unreliable.

[bold]Column divergence[/bold]  -- columns present on only one side, plus columns present on \
both sides but with a different dtype. Structural, like shape -- no values are compared.

[bold]Categorical divergence[/bold] -- of the file's categorical/label columns (allowed-value \
fields for patient; product_category/product_balance_status for product), how many have a \
label value on one side that never appears on the other? Also independent of the \
row-alignment key -- a distinct-value-set check per column, not tied to row identity.

[bold]Totals divergence[/bold]  -- of the file's numeric columns, how many have a column-sum \
that differs beyond a float tolerance? The first check that actually compares values, at the \
coarsest (whole-column) granularity.

[bold]Row-key divergence[/bold] -- rows whose full row-alignment key (all of it, not just the \
single identity column above) found no partner on the other side at all, counted per row, not \
per distinct key. A repeated key on one side with no matching repeat on the other also counts \
here -- that's the fan-out failure mode. This is what tells you whether Cell divergence below \
is measuring real disagreement or just has nothing to compare.

[bold]Cell divergence[/bold]    -- rows matched across R and Python (via the arm's \
row-alignment key), diffed value by value. The most granular value comparison -- but it's only \
meaningful once Row-key divergence above confirms the key actually paired the rows; 0 here can \
mean "everything agreed" or "nothing was paired to compare" (ticket 15/17 on the wayfinder map).\
"""


def _print_legend() -> None:
    console.print(Panel(LEGEND, title="What these columns measure", expand=False))


YEAR_PREFIX = re.compile(r"^(\d{4})_")


def _file_year(file_name: str) -> int | None:
    match = YEAR_PREFIX.match(file_name)
    return int(match.group(1)) if match else None


def _has_any_mismatch(file_comparison: FileComparison) -> bool:
    return (
        not file_comparison.shape.match
        or bool(file_comparison.columns.only_in_r)
        or bool(file_comparison.columns.only_in_py)
        or bool(file_comparison.columns.dtype_mismatches)
        or bool(file_comparison.totals)
        or bool(file_comparison.categorical_overlap)
        or bool(file_comparison.cell_mismatches)
        or file_comparison.row_key_overlap.r_unmatched > 0
        or file_comparison.row_key_overlap.py_unmatched > 0
        or (
            file_comparison.id_overlap is not None
            and bool(file_comparison.id_overlap.only_in_r or file_comparison.id_overlap.only_in_py)
        )
    )


def _print_summary(arm: str, comparison: DirectoryComparison, only_mismatches: bool) -> None:
    files = (
        [f for f in comparison.files if _has_any_mismatch(f)]
        if only_mismatches
        else comparison.files
    )
    if only_mismatches and not files:
        console.print(f"[green]{arm}: no mismatches in any file.[/green]")
        return

    by_year: dict[int | None, list] = {}
    for file_comparison in files:
        by_year.setdefault(_file_year(file_comparison.file_name), []).append(file_comparison)

    for year in sorted(by_year, key=lambda y: (y is None, -(y or 0))):
        title = f"{arm} — {year}" if year is not None else f"{arm} — unknown year"
        table = Table(title=title)
        table.add_column("File")
        table.add_column("Shape match")
        table.add_column("ID divergence (R-only / Py-only)")
        table.add_column("Column divergence", justify="right")
        table.add_column("Categorical divergence", justify="right")
        table.add_column("Totals divergence", justify="right")
        table.add_column("Row-key divergence (R-only / Py-only)")
        table.add_column("Cell divergence", justify="right")

        for file_comparison in by_year[year]:
            column_divergence = (
                len(file_comparison.columns.only_in_r)
                + len(file_comparison.columns.only_in_py)
                + len(file_comparison.columns.dtype_mismatches)
            )
            if file_comparison.id_overlap is None:
                id_divergence_str = "n/a"
            else:
                id_divergence_str = (
                    f"{len(file_comparison.id_overlap.only_in_r)} / "
                    f"{len(file_comparison.id_overlap.only_in_py)}"
                )
            row_key_str = (
                f"{file_comparison.row_key_overlap.r_unmatched} / "
                f"{file_comparison.row_key_overlap.py_unmatched}"
            )
            table.add_row(
                file_comparison.file_name,
                "✓" if file_comparison.shape.match else "✗",
                id_divergence_str,
                str(column_divergence),
                str(len(file_comparison.categorical_overlap)),
                str(len(file_comparison.totals)),
                row_key_str,
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


def _write_excel_report(path: Path, rows_by_sheet: dict[str, list[dict]]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, rows in rows_by_sheet.items():
        worksheet = workbook.create_sheet(sheet_name[:31])
        if not rows:
            worksheet.append(["(no mismatches)"])
            continue
        headers = list(rows[0].keys())
        worksheet.append(headers)
        for row in rows:
            worksheet.append([row[h] for h in headers])
    workbook.save(path)


@app.command()
def compare(
    r_dir: Annotated[Path, typer.Option("--r-dir", help="Root of the frozen R output directory")],
    py_dir: Annotated[Path, typer.Option("--py-dir", help="Root of the Python output directory")],
    report_out: Annotated[
        Path, typer.Option("--report-out", help="Where to write the Excel report")
    ] = Path("compare_report.xlsx"),
    only_mismatches: Annotated[
        bool,
        typer.Option(
            "--only-mismatches", help="Only print files with at least one measure flagged"
        ),
    ] = False,
) -> None:
    _print_legend()

    for label, subdir, key_cols, id_col, categorical_cols in STAGES:
        comparison = _compare_arm(
            r_dir / subdir, py_dir / subdir, key_cols, id_col, categorical_cols
        )
        _print_summary(label, comparison, only_mismatches)

        # One workbook per stage -- combining raw and cleaned into one per-column
        # aggregate would sum e.g. product_entry_date mismatches from both stages
        # into a single count, defeating the point of separating them.
        stage_report_out = report_out.with_stem(f"{report_out.stem}_{subdir}")
        summary_sheets = build_summary_rows(comparison, classifiers_by_column=CLASSIFIERS_BY_COLUMN)
        detail_sheets = build_mismatch_rows(comparison, classifiers_by_column=CLASSIFIERS_BY_COLUMN)
        _write_excel_report(stage_report_out, {**summary_sheets, **detail_sheets})

        console.print(f"[bold green]{label} report written to {stage_report_out}[/bold green]")


if __name__ == "__main__":
    app()
