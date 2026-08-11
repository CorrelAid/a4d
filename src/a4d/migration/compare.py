"""R-vs-Python output comparison for the migration (ticket 15).

Diffs two existing output directories (a Python run, the frozen R baseline)
across seven layers: shape (row count), ID divergence (identities present on
only one side), columns/dtypes, categorical divergence (label values present
on only one side, per column), aggregate totals, row-key overlap (rows whose
full row-alignment key found no partner on the other side, or fanned out via
a repeated key), and cell-by-cell -- the last two grouped together since both
depend on the same row-alignment key. This is migration-only tooling with a
defined end-of-life (R's retirement) -- deliberately not wired into
``a4d.cli``.
"""

import datetime
from collections import Counter
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
class RowKeyOverlap:
    matched: int
    r_unmatched: int
    py_unmatched: int


def compare_row_key_overlap(
    r_df: pl.DataFrame, py_df: pl.DataFrame, key_cols: list[str]
) -> RowKeyOverlap:
    r_counts = Counter(r_df.select(key_cols).iter_rows())
    py_counts = Counter(py_df.select(key_cols).iter_rows())

    matched = 0
    r_unmatched = 0
    py_unmatched = 0
    for key in r_counts.keys() | py_counts.keys():
        r_count, py_count = r_counts.get(key, 0), py_counts.get(key, 0)
        matched += min(r_count, py_count)
        r_unmatched += r_count - min(r_count, py_count)
        py_unmatched += py_count - min(r_count, py_count)

    return RowKeyOverlap(matched=matched, r_unmatched=r_unmatched, py_unmatched=py_unmatched)


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
    row_key_overlap: RowKeyOverlap
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
                row_key_overlap=compare_row_key_overlap(r_df, py_df, key_cols),
                cell_mismatches=compare_cells(r_df, py_df, key_cols),
            )
        )

    return DirectoryComparison(
        files=files,
        only_in_r=sorted(r_names - py_names),
        only_in_py=sorted(py_names - r_names),
    )


def build_mismatch_rows(
    comparison: DirectoryComparison,
    classifiers_by_column: dict[str, dict[str, Classifier]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    classifiers_by_column = classifiers_by_column or {}

    id_overlap_rows = []
    categorical_overlap_rows = []
    row_key_overlap_rows = []
    totals_rows = []
    cell_mismatch_rows = []

    for file_comparison in comparison.files:
        name = file_comparison.file_name

        row_key_overlap_rows.append(
            {
                "file": name,
                "matched": file_comparison.row_key_overlap.matched,
                "r_unmatched": file_comparison.row_key_overlap.r_unmatched,
                "py_unmatched": file_comparison.row_key_overlap.py_unmatched,
            }
        )

        if file_comparison.id_overlap is not None:
            for value in file_comparison.id_overlap.only_in_r:
                id_overlap_rows.append({"file": name, "side": "R only", "value": value})
            for value in file_comparison.id_overlap.only_in_py:
                id_overlap_rows.append({"file": name, "side": "Python only", "value": value})

        for overlap in file_comparison.categorical_overlap:
            for value in overlap.only_in_r:
                categorical_overlap_rows.append(
                    {"file": name, "column": overlap.column, "side": "R only", "value": value}
                )
            for value in overlap.only_in_py:
                categorical_overlap_rows.append(
                    {
                        "file": name,
                        "column": overlap.column,
                        "side": "Python only",
                        "value": value,
                    }
                )

        for totals_mismatch in file_comparison.totals:
            totals_rows.append(
                {
                    "file": name,
                    "column": totals_mismatch.column,
                    "r_total": totals_mismatch.r_total,
                    "py_total": totals_mismatch.py_total,
                    "diff": totals_mismatch.py_total - totals_mismatch.r_total,
                }
            )

        for mismatch in file_comparison.cell_mismatches:
            registry = classifiers_by_column.get(mismatch.column, {})
            cell_mismatch_rows.append(
                {
                    "file": name,
                    "key": "; ".join(f"{k}={v}" for k, v in mismatch.key.items()),
                    "column": mismatch.column,
                    "r_value": mismatch.r_value,
                    "py_value": mismatch.py_value,
                    "cause": classify(mismatch, registry),
                }
            )

    return {
        "id_overlap": id_overlap_rows,
        "categorical_overlap": categorical_overlap_rows,
        "row_key_overlap": row_key_overlap_rows,
        "totals": totals_rows,
        "cell_mismatches": cell_mismatch_rows,
    }


def build_summary_rows(
    comparison: DirectoryComparison,
    classifiers_by_column: dict[str, dict[str, Classifier]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    classifiers_by_column = classifiers_by_column or {}

    per_column: dict[str, int] = {}
    per_cause: dict[tuple[str, str], int] = {}
    for file_comparison in comparison.files:
        for mismatch in file_comparison.cell_mismatches:
            per_column[mismatch.column] = per_column.get(mismatch.column, 0) + 1
            registry = classifiers_by_column.get(mismatch.column, {})
            cause = classify(mismatch, registry)
            per_cause[(mismatch.column, cause)] = per_cause.get((mismatch.column, cause), 0) + 1

    return {
        "per_column": [
            {"column": col, "mismatches": count}
            for col, count in sorted(per_column.items(), key=lambda kv: -kv[1])
        ],
        "per_cause": [
            {"column": col, "cause": cause, "mismatches": count}
            for (col, cause), count in sorted(per_cause.items(), key=lambda kv: -kv[1])
        ],
        "only_in_r": [{"file": name} for name in comparison.only_in_r],
        "only_in_py": [{"file": name} for name in comparison.only_in_py],
    }
