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
        --output-dir output/comparison
"""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from loguru import logger
from openpyxl import Workbook
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from a4d.clean.schema import (
    get_date_columns,
    get_numeric_columns,
)
from a4d.clean.schema import (
    get_string_columns as get_patient_string_columns,
)
from a4d.migration.compare import (
    DERIVED_RUNNING_TOTAL_CLASSIFIERS,
    EXCEL_FORMULA_ERROR_CLASSIFIERS,
    PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    PATIENT_INSULIN_SUBTYPE_CLASSIFIERS,
    PATIENT_INSULIN_TOTAL_UNITS_CLASSIFIERS,
    PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS,
    PATIENT_RECRUITMENT_DATE_CLASSIFIERS,
    PATIENT_UNTRIMMED_VALIDATION_CLASSIFIERS,
    PRODUCT_CATEGORY_CLASSIFIERS,
    PRODUCT_ENTRY_DATE_CLASSIFIERS,
    PRODUCT_ROW_ORDER_CLASSIFIERS,
    R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS,
    STRAY_DATE_CLASSIFIERS,
    STRAY_DATE_ZEROED_CLASSIFIERS,
    WIDE_FORMAT_FRAGMENT_CLASSIFIERS,
    Delta,
    DirectoryComparison,
    FileComparison,
    add_row_ordinal,
    build_mismatch_rows,
    build_summary_rows,
    compare_directory,
    compute_deltas,
    normalize_date_column,
    normalize_numeric_column,
    normalize_whitespace_column,
    snapshot_from_summary,
    summarize_directory,
)

# normalize_date_column (via a4d.clean.date_parser.parse_date_flexible) logs
# at DEBUG per parsed value; loguru's default sink has no level filter, so
# without this every date cell would spam the console. This tool never calls
# a4d.logging.setup_logging() (no pipeline run, no output_root to log into).
#
# a4d.clean.* is silenced entirely, not just below WARNING: the date parser
# also warns once per value it cannot parse, which in the *pipeline* is a
# real data-quality signal but here is pure noise -- this tool feeds it raw
# free-text columns precisely to normalize the parseable ones, so
# unparseable cells are expected, not actionable, and at 18 date columns x
# ~245 files they drown the report the tool exists to print.
logger.remove()
logger.add(
    sys.stderr,
    level="WARNING",
    filter=lambda record: not record["name"].startswith("a4d.clean"),
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

# Raw-stage-only, derived from the cleaned schema's own pl.Date columns
# (ticket 23): the same representation gap ticket 20 found and fixed for
# product's raw product_entry_date -- R's raw extraction stores the
# unparsed source text (an Excel serial for date-formatted cells) while
# Python's raw extraction already ISO-formats parsed dates. Cleaned stage
# never needs this since both sides are already parsed dates there.
# meter_received_date (ticket 27) is appended by hand: it's a raw-only
# column absent from the cleaned schema entirely (no cleaned-stage
# equivalent), so get_date_columns() can't see it, but it carries the same
# raw-serial-vs-parsed representation gap -- verified against real drive
# data (1,761 mismatches collapsed to the same shape as the derived columns).
PATIENT_RAW_DATE_NORMALIZE_COLS = [*get_date_columns(), "meter_received_date"]

# Raw-stage-only (ticket 27, extending ticket 22's product_balance
# precedent to patient): R's own float-to-string conversion rounds a raw
# numeric column's trailing digits differently than Python's -- a
# representation difference cleaning's own type-casting already resolves.
# Derived from the cleaned schema's numeric columns rather than hand-listed,
# mirroring PATIENT_RAW_DATE_NORMALIZE_COLS's own precedent.
PATIENT_RAW_NUMERIC_NORMALIZE_COLS = get_numeric_columns()

# Ordinal position within (clinic_id, product_sheet_name) -- see
# add_row_ordinal's docstring. Replaces the old equi-join key (clinic_id,
# product, product_sheet_name, product_entry_date), which collapsed onto far
# fewer distinct values than rows exist wherever product_entry_date is null
# (ticket 17).
PRODUCT_ORDINAL_GROUP_COLS = ["clinic_id", "product_sheet_name"]
PRODUCT_ID_COL = "product"
PRODUCT_CATEGORICAL_COLS = ["product_category", "product_balance_status"]

# Raw-stage-only (ticket 24, extending ticket 22's product_balance precedent):
# R's own float-to-string conversion rounds a raw numeric column's trailing
# digits differently -- same representation gap product_balance already had,
# just not yet wired for these three quantity columns.
PRODUCT_RAW_NUMERIC_NORMALIZE_COLS = [
    "product_balance",
    "product_units_received",
    "product_units_released",
    "product_received_from",
]

# Raw-stage-only (ticket 22): readxl's trim_ws=TRUE default strips whitespace
# R-side that openpyxl-based Python extraction preserves as-is. Every raw
# string column except product_entry_date (date-normalized instead) and
# product_balance (numeric-normalized instead).
PRODUCT_RAW_WHITESPACE_NORMALIZE_COLS = [
    "product",
    "product_received_from",
    "product_released_to",
    "product_remarks",
    "product_units_received",
    "product_units_released",
    "product_units_returned",
    "product_returned_by",
]

# ticket 21: unlike the other raw-stage-only normalizations, an embedded
# \r\n-vs-\n line break survives cleaning (step 2.16's str.strip_chars only
# trims ends) and still shows up on `product` at the cleaned stage --
# verified directly against the real R/Python cleaned output pair (e.g.
# "FastClix \r\nLancets" vs "FastClix \nLancets"). Scoped to `product` alone:
# it's the only cleaned-stage column found carrying multi-line values: rest
# were already fully explained by PRODUCT_ROW_ORDER_CLASSIFIERS.
# ticket 36 extends this to the two identifier columns. Both pipelines now
# trim every string cell; R trims only product_released_to, so R keeps a
# stray space the source really carries (sheet tab "Dec24 ", file
# "... - final .xlsx"). A settled representation difference, so the report
# should stop counting it as divergence.
PRODUCT_CLEANED_WHITESPACE_NORMALIZE_COLS = ["product", "product_sheet_name", "file_name"]

# ticket 36: patient cleaning now trims too, and sheet_name is half the
# patient row-alignment key -- without this, R's untrimmed "Dec24 " would
# fail to join Python's "Dec24" and drop those rows from the comparison
# entirely rather than showing them as equal.
# Derived from the patient schema rather than hand-listed. R's cleaned patient
# output keeps the trailing whitespace its source cells carry (measured: ~3,750
# cells across edu_occ, observations, name, family_history and others), which
# Python's cleaning now strips -- a settled representation difference, and the
# same treatment ticket 22 gave product's raw stage. sheet_name matters most:
# it is half the patient row-alignment key, so without this R's untrimmed
# "Dec24 " would fail to join Python's "Dec24" and drop those rows from the
# comparison entirely rather than showing them as equal.
PATIENT_WHITESPACE_NORMALIZE_COLS = get_patient_string_columns()

CLASSIFIERS_BY_COLUMN = {
    # ticket 28: R's static "Patient List" recruitment-date extraction fails
    # to populate recruitment_date for most patients even where the tracker
    # plainly records one -- verified against the real source Excel.
    "recruitment_date": PATIENT_RECRUITMENT_DATE_CLASSIFIERS,
    # ticket 28: R's own allowed-values validator rejects the multi-insulin
    # CSV output R's own derivation logic produces for 2024+ trackers --
    # already documented as a deliberate Python correction in
    # _derive_insulin_fields's docstring (src/a4d/clean/patient.py).
    "insulin_subtype": PATIENT_INSULIN_SUBTYPE_CLASSIFIERS,
    # ticket 36: R rejects a source value for its trailing whitespace alone
    # and sentinels it; Python now trims before validating and keeps it.
    "sex": PATIENT_UNTRIMMED_VALIDATION_CLASSIFIERS,
    # ticket 27: bmi and t1d_diagnosis_age are formula-derived in the source
    # trackers -- a source formula error (height 0, an unparseable date)
    # leaves R's raw extraction holding the literal Excel error string,
    # while Python's raw extraction (openpyxl, data_only) has no cached
    # value to carry and returns null. age shares the same shape on a
    # handful of rows. Verified against the real drive data.
    "bmi": EXCEL_FORMULA_ERROR_CLASSIFIERS,
    "t1d_diagnosis_age": EXCEL_FORMULA_ERROR_CLASSIFIERS,
    "age": EXCEL_FORMULA_ERROR_CLASSIFIERS,
    # ticket 27: source-data typos where a clinician entered a Thai
    # Buddhist-Era year into a Gregorian date cell -- see
    # PATIENT_BUDDHIST_ERA_CLASSIFIERS's docstring. Every raw-stage date
    # column found carrying this pattern against the real drive data.
    "bmi_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "hba1c_updated_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "blood_pressure_updated": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "fbg_updated_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "last_clinic_visit_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "hospitalisation_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "complication_screening_kidney_test_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "complication_screening_lipid_profile_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "complication_screening_thyroid_test_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "complication_screening_eye_exam_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    # ticket 36: the entry-date-specific causes are checked first (they are
    # source-verified and stage-specific), then the row-order fallback every
    # positionally-aligned product column carries. R's readxl nulls the
    # *text*-formatted cells of a mixed-type Entry Date column (verified: 2022
    # Vietnam National Children's Hospital, Apr22, where "20/04/2022" is
    # stored as text and "2022-04-01" as a datetime), which drops R back to
    # input-order sorting -- so both sides hold a real, different date and
    # `r_value_missing` never fires.
    "product_entry_date": PRODUCT_ENTRY_DATE_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_category": PRODUCT_CATEGORY_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 21: cleaned-stage columns whose mismatches are dominated by a
    # within-(clinic, sheet) sort-order divergence, not genuine content
    # differences -- see PRODUCT_ROW_ORDER_CLASSIFIERS's docstring.
    # ticket 36: the endpoint test comes first -- it is the order-independent
    # evidence for a derived running total, where the membership heuristic
    # under-detects by construction (27.9% caught, ticket 21's "future work").
    "product_balance": DERIVED_RUNNING_TOTAL_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 24: also carries the raw-stage stray-date-typed-cell cause --
    # merged since CLASSIFIERS_BY_COLUMN holds one registry per column across
    # every stage. Stray-date checked first: row_order_candidate is a loose
    # "this value appears elsewhere in the group" heuristic that false-fires
    # on common small values like "0", so it must not shadow the more
    # specific, source-verified stray-date match.
    "product_received_from": STRAY_DATE_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_released_to": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_remarks": PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 36: STRAY_DATE_ZEROED_CLASSIFIERS is the cleaned-stage face of the
    # same cause and must, like the raw-stage one, precede the loose row-order
    # heuristic -- "0" appears all over a group, so row_order_candidate
    # false-fires on it.
    "product_units_received": STRAY_DATE_CLASSIFIERS
    | STRAY_DATE_ZEROED_CLASSIFIERS
    | PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product": PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 36: the remaining schema columns, wired so no positionally
    # aligned column is left without the row-order fallback.
    "product_units_notes": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_units_returned": STRAY_DATE_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_returned_by": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_balance_status": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "orig_product_released_to": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_unit_capacity": PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 24: raw-stage wide-format comma/hyphen split ambiguity (2017-2019
    # Mandalay files). ticket 25 adds the row-order cause for the cleaned
    # stage, which this column shares with every sibling above -- it was
    # omitted when ticket 21 named six columns and not this one, leaving
    # 2,144 cleaned-stage mismatches reported as unclassified. Wide-format
    # first (it is source-verified and stage-specific); measured against the
    # real drive data, it matches nothing at the cleaned stage, so the order
    # only guards the raw stage's existing classification.
    "product_units_released": WIDE_FORMAT_FRAGMENT_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 29: R's insulin-column dedup grep deletes "TOTAL Insulin Units"
    # from every 2024+ tracker before it is read, so R's column is null on all
    # 81,859 rows while Python reads it correctly.
    "insulin_total_units": PATIENT_INSULIN_TOTAL_UNITS_CLASSIFIERS,
    # ticket 29: R's Patient List join suffixes both sides on a name
    # collision, so R's cleaning finds no unsuffixed column and leaves these
    # null for the whole file (21 files / 3 files respectively).
    "fbg_baseline_mg": PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS,
    "fbg_baseline_mmol": PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS,
}

# ticket 29: R's 999999 numeric sentinel is not a property of any one column
# -- R stamps it on any numeric cell whose source text failed to parse -- so
# it is derived from the patient schema's own numeric column list rather than
# hand-listed. Appended after each column's specific causes so a
# source-verified, column-specific classifier still wins the first match.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS
    for col in get_numeric_columns()
}

# (label, output subdir, row-alignment key or ordinal-group cols, identity
# column, categorical columns, ordinal_group_cols, date_normalize_cols,
# numeric_normalize_cols, whitespace_normalize_cols). Raw and cleaned are
# compared separately so a divergence can be localized to extraction vs.
# cleaning; categorical columns listed here that don't exist yet at the raw
# stage are silently skipped by compare_categorical_overlap.
# date_normalize_cols is raw-stage-only (ticket 20): R's raw extraction
# stores unparsed source date text (an Excel serial for date-formatted
# cells) while Python's raw extraction already ISO-formats parsed dates --
# a representation difference, not a real divergence, that the cleaned
# stage never has since both sides are already parsed dates there.
# numeric_normalize_cols is raw-stage-only (ticket 22): R's own
# float-to-string conversion rounds a raw numeric column's trailing digits
# differently, a representation difference cleaning's own type-casting (step
# 2.16) already resolves. whitespace_normalize_cols mostly is too (readxl's
# trim_ws=TRUE trims R-side what Python's raw extraction preserves), but an
# embedded \r\n-vs-\n line break isn't touched by cleaning's end-trim-only
# str.strip_chars and survives into `product` at the cleaned stage (ticket 21).
STAGES = [
    (
        "Patient (raw)",
        "patient_data_raw",
        PATIENT_KEY_COLS,
        PATIENT_ID_COL,
        PATIENT_CATEGORICAL_COLS,
        None,
        PATIENT_RAW_DATE_NORMALIZE_COLS,
        PATIENT_RAW_NUMERIC_NORMALIZE_COLS,
        PATIENT_WHITESPACE_NORMALIZE_COLS,
    ),
    (
        "Patient (cleaned)",
        "patient_data_cleaned",
        PATIENT_KEY_COLS,
        PATIENT_ID_COL,
        PATIENT_CATEGORICAL_COLS,
        None,
        None,
        None,
        PATIENT_WHITESPACE_NORMALIZE_COLS,
    ),
    (
        "Product (raw)",
        "product_data_raw",
        None,
        PRODUCT_ID_COL,
        PRODUCT_CATEGORICAL_COLS,
        PRODUCT_ORDINAL_GROUP_COLS,
        ["product_entry_date"],
        PRODUCT_RAW_NUMERIC_NORMALIZE_COLS,
        PRODUCT_RAW_WHITESPACE_NORMALIZE_COLS,
    ),
    (
        "Product (cleaned)",
        "product_data_cleaned",
        None,
        PRODUCT_ID_COL,
        PRODUCT_CATEGORICAL_COLS,
        PRODUCT_ORDINAL_GROUP_COLS,
        None,
        None,
        PRODUCT_CLEANED_WHITESPACE_NORMALIZE_COLS,
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
    r_dir: Path,
    py_dir: Path,
    key_cols: list[str] | None,
    id_col: str,
    categorical_cols: list[str],
    ordinal_group_cols: list[str] | None = None,
    date_normalize_cols: list[str] | None = None,
    numeric_normalize_cols: list[str] | None = None,
    whitespace_normalize_cols: list[str] | None = None,
) -> DirectoryComparison:
    r_frames = _load_parquet_dir(r_dir)
    py_frames = _load_parquet_dir(py_dir)
    for column in date_normalize_cols or []:
        for frames in (r_frames, py_frames):
            for name, df in frames.items():
                frames[name] = normalize_date_column(df, column)
    # Whitespace before numeric (ticket 24): normalize_numeric_column widens a
    # column to `pl.Object` (mixed float/str) the moment any value parses,
    # which breaks normalize_whitespace_column's `.str.*` expressions on the
    # non-numeric residual if applied after -- stripping first keeps the
    # column `pl.String` for numeric normalization to then act on.
    for column in whitespace_normalize_cols or []:
        for frames in (r_frames, py_frames):
            for name, df in frames.items():
                frames[name] = normalize_whitespace_column(df, column)
    for column in numeric_normalize_cols or []:
        for frames in (r_frames, py_frames):
            for name, df in frames.items():
                frames[name] = normalize_numeric_column(df, column)
    order_group_cols = None
    if ordinal_group_cols is not None:
        resolved_key_cols = None
        for frames in (r_frames, py_frames):
            for name, df in frames.items():
                frames[name], resolved_key_cols = add_row_ordinal(df, ordinal_group_cols)
        key_cols = resolved_key_cols
        # Everything add_row_ordinal returned except the trailing ordinal
        # itself -- the group a within-group sort-order divergence (ticket
        # 21) is scoped to.
        order_group_cols = resolved_key_cols[:-1]
    assert key_cols is not None
    # __-prefixed helper columns from add_row_ordinal are join-key-only synthetic
    # data (an ordinal counter, normalized group values) -- summing/diffing them
    # as if they were real output columns would be noise, not signal.
    numeric_cols = [c for c in _numeric_cols(r_frames) if not c.startswith("__")]
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
        order_group_cols=order_group_cols,
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

    _render_arm_totals(arm, comparison)

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


def _render_arm_totals(arm: str, comparison: DirectoryComparison) -> None:
    """Whole-arm rollup, printed after the per-year tables.

    The per-year tables say *where* a divergence is; without this you can
    only get *how much* there is by scrolling and adding up every year.
    """
    summary = summarize_directory(comparison)

    table = Table(title=f"{arm} — totals across all {summary.files_compared} files compared")
    table.add_column("Measure")
    table.add_column("Files affected", justify="right")
    table.add_column("Total", justify="right")

    def add(measure: str, value: tuple[int, int]) -> None:
        files_affected, total = value
        style = "" if total == 0 else "yellow"
        table.add_row(measure, str(files_affected), str(total), style=style)

    shape_style = "" if summary.shape_mismatch_files == 0 else "yellow"
    table.add_row("Shape mismatch", str(summary.shape_mismatch_files), "—", style=shape_style)
    add("ID divergence", summary.id_divergence)
    add("Column divergence", summary.column_divergence)
    add("Categorical divergence", summary.categorical_divergence)
    add("Totals divergence", summary.totals_divergence)
    add("Row-key divergence", summary.row_key_divergence)
    add("Cell divergence", summary.cell_divergence)

    console.print(table)

    if summary.only_in_r or summary.only_in_py:
        console.print(
            f"[yellow]Files on only one side:[/yellow] "
            f"{summary.only_in_r} R-only, {summary.only_in_py} Python-only "
            f"(not included in the counts above — nothing to compare them against)"
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


def _previous_run_dirs(output_dir: Path, current_run_dir: Path) -> list[Path]:
    # Run directories are named by ISO-8601 timestamp, so lexicographic sort is
    # chronological -- most recent first, excluding the run just created.
    if not output_dir.exists():
        return []
    run_dirs = [p for p in output_dir.iterdir() if p.is_dir() and p != current_run_dir]
    return sorted(run_dirs, reverse=True)


def _load_latest_snapshot(
    output_dir: Path, current_run_dir: Path, subdir: str
) -> dict[str, dict[str, int]] | None:
    # A stage can be missing from an older run (e.g. it errored, or the stage
    # set changed) -- walk back further rather than only checking the single
    # most recent run directory.
    for run_dir in _previous_run_dirs(output_dir, current_run_dir):
        snapshot_path = run_dir / f"snapshot_{subdir}.json"
        if snapshot_path.exists():
            return json.loads(snapshot_path.read_text())
    return None


def _write_snapshot(run_dir: Path, subdir: str, snapshot: dict[str, dict[str, int]]) -> Path:
    path = run_dir / f"snapshot_{subdir}.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
    return path


def _print_deltas(label: str, column_deltas: list[Delta], cause_deltas: list[Delta]) -> None:
    if not column_deltas and not cause_deltas:
        console.print(f"[dim]{label}: no change from the previous run.[/dim]")
        return

    table = Table(title=f"{label} — change since previous run")
    table.add_column("Column")
    table.add_column("Previous", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Diff", justify="right")
    for delta in column_deltas:
        diff = delta.current - delta.previous
        style = "red" if diff > 0 else "green"
        table.add_row(
            delta.key, str(delta.previous), str(delta.current), f"[{style}]{diff:+d}[/{style}]"
        )
    console.print(table)


def _delta_rows(deltas: list[Delta]) -> list[dict]:
    return [
        {
            "key": delta.key,
            "previous": delta.previous,
            "current": delta.current,
            "diff": delta.current - delta.previous,
        }
        for delta in deltas
    ]


@app.command()
def compare(
    r_dir: Annotated[Path, typer.Option("--r-dir", help="Root of the frozen R output directory")],
    py_dir: Annotated[Path, typer.Option("--py-dir", help="Root of the Python output directory")],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir", help="Directory each run's own timestamped subfolder is created under"
        ),
    ] = Path("output/comparison"),
    only_mismatches: Annotated[
        bool,
        typer.Option(
            "--only-mismatches", help="Only print files with at least one measure flagged"
        ),
    ] = False,
) -> None:
    _print_legend()
    # Every stage of this run shares one timestamped subfolder, so a run is a
    # single self-contained unit on disk -- its reports and snapshots (for the
    # *next* run's delta) live together, and nothing gets overwritten by a
    # later run.
    run_dir = output_dir / datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    for (
        label,
        subdir,
        key_cols,
        id_col,
        categorical_cols,
        ordinal_group_cols,
        date_normalize_cols,
        numeric_normalize_cols,
        whitespace_normalize_cols,
    ) in STAGES:
        comparison = _compare_arm(
            r_dir / subdir,
            py_dir / subdir,
            key_cols,
            id_col,
            categorical_cols,
            ordinal_group_cols,
            date_normalize_cols,
            numeric_normalize_cols,
            whitespace_normalize_cols,
        )
        _print_summary(label, comparison, only_mismatches)

        # One workbook per stage -- combining raw and cleaned into one per-column
        # aggregate would sum e.g. product_entry_date mismatches from both stages
        # into a single count, defeating the point of separating them.
        stage_report_out = run_dir / f"compare_report_{subdir}.xlsx"
        summary_sheets = build_summary_rows(comparison, classifiers_by_column=CLASSIFIERS_BY_COLUMN)
        detail_sheets = build_mismatch_rows(comparison, classifiers_by_column=CLASSIFIERS_BY_COLUMN)

        # Run-over-run history (ticket 19): compare this run's per-column/per-cause
        # counts against the most recent prior run's snapshot for this stage, so a
        # triage fix's actual effect (or a regression) is visible directly rather
        # than only ever seeing the current numbers.
        current_snapshot = snapshot_from_summary(summary_sheets)
        previous_snapshot = _load_latest_snapshot(output_dir, run_dir, subdir)
        column_deltas = (
            compute_deltas(previous_snapshot["per_column"], current_snapshot["per_column"])
            if previous_snapshot
            else []
        )
        cause_deltas = (
            compute_deltas(previous_snapshot["per_cause"], current_snapshot["per_cause"])
            if previous_snapshot
            else []
        )
        if previous_snapshot is None:
            console.print(f"[dim]{label}: no previous run to compare against.[/dim]")
        else:
            _print_deltas(label, column_deltas, cause_deltas)
        history_sheets = {
            "history_column_deltas": _delta_rows(column_deltas),
            "history_cause_deltas": _delta_rows(cause_deltas),
        }
        _write_snapshot(run_dir, subdir, current_snapshot)

        _write_excel_report(stage_report_out, {**summary_sheets, **detail_sheets, **history_sheets})

        console.print(f"[bold green]{label} report written to {stage_report_out}[/bold green]")


if __name__ == "__main__":
    app()
