"""R-vs-Python output comparison for the migration (ticket 15).

Diffs two existing output directories (a Python run, the frozen R baseline)
in four increasingly granular layers: shape, aggregate totals, columns/dtypes,
cell-by-cell. This is migration-only tooling with a defined end-of-life (R's
retirement) -- deliberately not wired into ``a4d.cli``.
"""

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import polars as pl

SENTINEL_DATE = datetime.date(9999, 9, 9)


@dataclass(frozen=True)
class ShapeResult:
    r_rows: int
    py_rows: int
    match: bool


def compare_shape(r_df: pl.DataFrame, py_df: pl.DataFrame) -> ShapeResult:
    r_rows, py_rows = len(r_df), len(py_df)
    return ShapeResult(r_rows=r_rows, py_rows=py_rows, match=r_rows == py_rows)


@dataclass(frozen=True)
class TotalsMismatch:
    column: str
    r_total: float
    py_total: float


TOTALS_REL_TOL = 1e-9
TOTALS_ABS_TOL = 1e-6


def compare_totals(
    r_df: pl.DataFrame, py_df: pl.DataFrame, numeric_cols: list[str]
) -> list[TotalsMismatch]:
    mismatches = []
    for col in numeric_cols:
        if col not in r_df.columns or col not in py_df.columns:
            continue
        r_total = float(r_df[col].sum() or 0.0)
        py_total = float(py_df[col].sum() or 0.0)
        tolerance = max(TOTALS_REL_TOL * max(abs(r_total), abs(py_total)), TOTALS_ABS_TOL)
        if abs(r_total - py_total) > tolerance:
            mismatches.append(TotalsMismatch(column=col, r_total=r_total, py_total=py_total))
    return mismatches


@dataclass(frozen=True)
class ColumnsResult:
    only_in_r: list[str]
    only_in_py: list[str]
    dtype_mismatches: list[tuple[str, pl.DataType, pl.DataType]]


def compare_columns(r_df: pl.DataFrame, py_df: pl.DataFrame) -> ColumnsResult:
    r_cols, py_cols = set(r_df.columns), set(py_df.columns)
    common = sorted(r_cols & py_cols)
    dtype_mismatches = [
        (col, r_df.schema[col], py_df.schema[col])
        for col in common
        if r_df.schema[col] != py_df.schema[col]
    ]
    return ColumnsResult(
        only_in_r=sorted(r_cols - py_cols),
        only_in_py=sorted(py_cols - r_cols),
        dtype_mismatches=dtype_mismatches,
    )


@dataclass(frozen=True)
class IdOverlapResult:
    only_in_r: list[Any]
    only_in_py: list[Any]
    common_count: int


def compare_id_overlap(r_df: pl.DataFrame, py_df: pl.DataFrame, id_col: str) -> IdOverlapResult:
    r_ids = set(r_df[id_col].drop_nulls().to_list())
    py_ids = set(py_df[id_col].drop_nulls().to_list())
    return IdOverlapResult(
        only_in_r=sorted(r_ids - py_ids),
        only_in_py=sorted(py_ids - r_ids),
        common_count=len(r_ids & py_ids),
    )


@dataclass(frozen=True)
class CategoricalOverlap:
    column: str
    only_in_r: list[Any]
    only_in_py: list[Any]


def compare_categorical_overlap(
    r_df: pl.DataFrame, py_df: pl.DataFrame, categorical_cols: list[str]
) -> list[CategoricalOverlap]:
    mismatches = []
    for col in categorical_cols:
        if col not in r_df.columns or col not in py_df.columns:
            continue
        overlap = compare_id_overlap(r_df, py_df, col)
        if overlap.only_in_r or overlap.only_in_py:
            mismatches.append(
                CategoricalOverlap(
                    column=col, only_in_r=overlap.only_in_r, only_in_py=overlap.only_in_py
                )
            )
    return mismatches


@dataclass(frozen=True)
class CellMismatch:
    key: dict[str, Any]
    column: str
    r_value: Any
    py_value: Any


CELL_FLOAT_REL_TOL = 1e-9
CELL_FLOAT_ABS_TOL = 1e-9


def _values_differ(r_value: Any, py_value: Any) -> bool:
    if r_value is None or py_value is None:
        return r_value != py_value
    if isinstance(r_value, float) and isinstance(py_value, float):
        tolerance = max(CELL_FLOAT_REL_TOL * max(abs(r_value), abs(py_value)), CELL_FLOAT_ABS_TOL)
        return abs(r_value - py_value) > tolerance
    return r_value != py_value


def compare_cells(
    r_df: pl.DataFrame, py_df: pl.DataFrame, key_cols: list[str]
) -> list[CellMismatch]:
    joined = r_df.join(py_df, on=key_cols, how="inner", suffix="_py")
    value_cols = [c for c in r_df.columns if c not in key_cols and c in py_df.columns]

    mismatches = []
    for row in joined.iter_rows(named=True):
        key = {k: row[k] for k in key_cols}
        for col in value_cols:
            r_value, py_value = row[col], row[f"{col}_py"]
            if _values_differ(r_value, py_value):
                mismatches.append(
                    CellMismatch(key=key, column=col, r_value=r_value, py_value=py_value)
                )
    return mismatches


Classifier = Callable[[CellMismatch], bool]


def classify(mismatch: CellMismatch, registry: dict[str, Classifier]) -> str:
    for cause_name, classifier in registry.items():
        if classifier(mismatch):
            return cause_name
    return "unclassified"


# Seeded from the four causes already identified in the parity-presentation PDF
# for Product_entry_date (docs/migration/Product pipeline parity presentation.pdf).
# These are heuristics on the parsed (r_value, py_value) pair alone -- refining
# them, or adding new named causes, against real flagged rows is ticket 15's job.
CE_TYPO_YEAR_THRESHOLD = 2100


def _is_sentinel_null(m: CellMismatch) -> bool:
    return m.r_value is None and m.py_value == SENTINEL_DATE


def _is_typo_rescue(m: CellMismatch) -> bool:
    return m.r_value is None and m.py_value is not None and m.py_value != SENTINEL_DATE


def _is_ce_typo(m: CellMismatch) -> bool:
    return isinstance(m.r_value, datetime.date) and m.r_value.year > CE_TYPO_YEAR_THRESHOLD


def _is_off_by_one_day(m: CellMismatch) -> bool:
    return (
        isinstance(m.r_value, datetime.date)
        and isinstance(m.py_value, datetime.date)
        and m.r_value != SENTINEL_DATE
        and m.py_value != SENTINEL_DATE
        and abs((m.r_value - m.py_value).days) == 1
    )


PRODUCT_ENTRY_DATE_CLASSIFIERS: dict[str, Classifier] = {
    "sentinel_null": _is_sentinel_null,
    "typo_rescue": _is_typo_rescue,
    "ce_typo": _is_ce_typo,
    "off_by_one_day": _is_off_by_one_day,
}


@dataclass(frozen=True)
class FileComparison:
    file_name: str
    shape: ShapeResult
    totals: list[TotalsMismatch]
    columns: ColumnsResult
    id_overlap: IdOverlapResult | None
    categorical_overlap: list[CategoricalOverlap]
    cell_mismatches: list[CellMismatch]


@dataclass(frozen=True)
class DirectoryComparison:
    files: list[FileComparison]
    only_in_r: list[str]
    only_in_py: list[str]


def compare_directory(
    r_frames: dict[str, pl.DataFrame],
    py_frames: dict[str, pl.DataFrame],
    key_cols: list[str],
    numeric_cols: list[str] | None = None,
    id_col: str | None = None,
    categorical_cols: list[str] | None = None,
) -> DirectoryComparison:
    numeric_cols = numeric_cols or []
    categorical_cols = categorical_cols or []
    r_names, py_names = set(r_frames), set(py_frames)
    common = sorted(r_names & py_names)

    files = []
    for name in common:
        r_df, py_df = r_frames[name], py_frames[name]
        files.append(
            FileComparison(
                file_name=name,
                shape=compare_shape(r_df, py_df),
                totals=compare_totals(r_df, py_df, numeric_cols),
                columns=compare_columns(r_df, py_df),
                id_overlap=compare_id_overlap(r_df, py_df, id_col) if id_col else None,
                categorical_overlap=compare_categorical_overlap(r_df, py_df, categorical_cols),
                cell_mismatches=compare_cells(r_df, py_df, key_cols),
            )
        )

    return DirectoryComparison(
        files=files,
        only_in_r=sorted(r_names - py_names),
        only_in_py=sorted(py_names - r_names),
    )


def _rows(headers: list[str], rows: list[tuple]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def render_html_report(
    comparison: DirectoryComparison,
    classifiers_by_column: dict[str, dict[str, Classifier]] | None = None,
) -> str:
    classifiers_by_column = classifiers_by_column or {}

    per_column: dict[str, int] = {}
    per_cause: dict[tuple[str, str], int] = {}
    for file_comparison in comparison.files:
        for mismatch in file_comparison.cell_mismatches:
            per_column[mismatch.column] = per_column.get(mismatch.column, 0) + 1
            registry = classifiers_by_column.get(mismatch.column, {})
            cause = classify(mismatch, registry)
            per_cause[(mismatch.column, cause)] = per_cause.get((mismatch.column, cause), 0) + 1

    column_table = _rows(
        ["column", "mismatches"], sorted(per_column.items(), key=lambda kv: -kv[1])
    )
    cause_table = _rows(
        ["column", "cause", "mismatches"],
        sorted(
            ((col, cause, count) for (col, cause), count in per_cause.items()),
            key=lambda row: -row[2],
        ),
    )
    only_in_r = "".join(f"<li>{name}</li>" for name in comparison.only_in_r)
    only_in_py = "".join(f"<li>{name}</li>" for name in comparison.only_in_py)

    legend = (
        "<dl>"
        "<dt><b>Shape match</b></dt>"
        "<dd>Do R and Python have the same row count for this file? A coarse structural "
        "check: matching shape says nothing about whether individual cell values agree.</dd>"
        "<dt><b>ID overlap</b></dt>"
        "<dd>Do the same identities (patient_id for patient, product name for product) "
        "appear on both sides at all, regardless of row count? Independent of the "
        "row-alignment key used for cell mismatches -- catches a patient or product "
        "dropped entirely, even when that key is unreliable.</dd>"
        "<dt><b>Column diffs</b></dt>"
        "<dd>Columns present on only one side, plus columns present on both sides but "
        "with a different dtype. Structural, like shape -- no values are compared.</dd>"
        "<dt><b>Totals mismatches</b></dt>"
        "<dd>Of the file's numeric columns, how many have a column-sum that differs "
        "beyond a float tolerance? The first check that actually compares values, at the "
        "coarsest (whole-column) granularity.</dd>"
        "<dt><b>Cell mismatches</b></dt>"
        "<dd>Rows matched across R and Python (via the arm's row-alignment key), diffed "
        "value by value. The most granular value comparison -- but it's only "
        "trustworthy if the row-alignment key is actually unique per row.</dd>"
        "</dl>"
    )

    return (
        "<html><body>"
        "<h1>R vs Python output comparison</h1>"
        f"<h2>What these measures mean</h2>{legend}"
        f"<h2>Per-column mismatches</h2>{column_table}"
        f"<h2>Per-cause mismatches</h2>{cause_table}"
        f"<h2>Files only in R</h2><ul>{only_in_r}</ul>"
        f"<h2>Files only in Python</h2><ul>{only_in_py}</ul>"
        "</body></html>"
    )
