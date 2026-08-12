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

from a4d.clean.date_parser import parse_date_flexible

SENTINEL_DATE = datetime.date(9999, 9, 9)


def normalize_date_column(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Parse a raw string date column to a common ``date`` representation.

    R's raw extraction stores dates as unparsed source text -- an Excel
    serial number (e.g. "42872.0") for cells Excel itself formats as dates,
    or the literal free-text string otherwise -- while Python's raw
    extraction already ISO-formats parsed dates. Comparing the two as raw
    strings treats that representation difference as a false mismatch on
    ~99% of product_entry_date rows (ticket 20). Reuses the same flexible
    parser the cleaning stage already applies (including its Excel-serial
    and typo handling), so a genuinely different underlying date -- not
    just a different spelling of the same one -- still surfaces as a real
    divergence.

    A column absent from ``df`` entirely is a no-op, matching
    ``add_row_ordinal``'s convention for raw output that isn't
    schema-normalized.
    """
    if column not in df.columns:
        return df
    parsed = [parse_date_flexible(v) for v in df[column]]
    return df.with_columns(pl.Series(column, parsed, dtype=pl.Date))


def normalize_numeric_column(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Parse a raw numeric-string column to ``float`` so float tolerance applies.

    R's and Python's own float-to-string conversions round a binary float's
    trailing digits differently (e.g. "9.300000000000001" vs "9.3" for the
    same value) -- a representation difference, not a real divergence, that
    ``_values_differ``'s float tolerance already handles once both sides are
    parsed back to ``float`` rather than compared as strings. A value that
    isn't numeric (product_units_received's raw column also holds text like
    "START BALANCE") passes through unchanged, so it still surfaces as an
    ordinary string mismatch if it genuinely differs.
    """
    if column not in df.columns:
        return df

    def _try_float(value: Any) -> Any:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return value

    parsed = [_try_float(v) for v in df[column]]
    return df.with_columns(pl.Series(column, parsed, dtype=pl.Object))


def normalize_whitespace_column(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Strip leading/trailing whitespace from a raw string column.

    readxl's ``read_xlsx`` (R's raw extraction) trims whitespace from every
    character column by default (``trim_ws = TRUE``) and represents an
    embedded line break as ``\\r\\n``; openpyxl-based Python extraction
    preserves a cell's leading/trailing whitespace exactly as stored and
    normalizes embedded breaks to ``\\n`` alone. Both defaults are
    representation differences, not real divergences -- verified against
    real raw output (ticket 22), where together they account for the large
    majority of non-numeric, non-date raw-stage product column mismatches.
    A whitespace-only cell strips to an empty string, which R's own
    ``trim_ws`` reduces further to NA, so this normalizes that too.
    """
    if column not in df.columns:
        return df
    stripped = pl.col(column).str.replace_all("\r\n", "\n").str.strip_chars()
    return df.with_columns(pl.when(stripped == "").then(None).otherwise(stripped).alias(column))


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


def add_row_ordinal(
    df: pl.DataFrame, group_cols: list[str], ordinal_col: str = "__row_ordinal"
) -> tuple[pl.DataFrame, list[str]]:
    """Add a within-group ordinal-position row-alignment key (ticket 17).

    Product's natural key -- (clinic_id, product, product_sheet_name,
    product_entry_date) -- collapses onto far fewer distinct values than rows
    exist wherever product_entry_date is null, causing join fan-out. Ordinal
    position within (clinic_id, product_sheet_name), taken in each file's
    existing row order, is a substitute validated directly against the real
    R/Python output pair: ~99.99% of product rows align cleanly on it, with
    the handful of exceptions being real, separately diagnosable divergences
    (a clinic_id typo, un-trimmed sheet names) rather than a key design flaw.

    Group columns are whitespace-normalized for the join key only -- the
    original column values are untouched, so e.g. a trailing space in R's
    product_sheet_name still surfaces as an ordinary cell mismatch on that
    column instead of silently breaking alignment for the whole group.

    A group column absent from ``df`` entirely (raw output isn't
    schema-normalized -- a columnless file is possible, e.g. a
    pre-product-tracking tracker year) keys as null rather than raising;
    such a file is empty anyway and never reaches the join.
    """
    group_key_cols = []
    exprs = []
    for col in group_cols:
        key_col = f"__key_{col}"
        if col not in df.columns:
            exprs.append(pl.repeat(None, df.height, dtype=pl.Null).alias(key_col))
            group_key_cols.append(key_col)
            continue
        expr = pl.col(col)
        if df.schema[col] == pl.Utf8:
            expr = expr.str.strip_chars()
        exprs.append(expr.alias(key_col))
        group_key_cols.append(key_col)
    df = df.with_columns(exprs)
    df = df.with_columns(pl.int_range(pl.len()).over(group_key_cols).alias(ordinal_col))
    return df, [*group_key_cols, ordinal_col]


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
    # Set by compare_cells when order_group_cols is given: True if r_value
    # appears anywhere in the Python side's own group for this column --
    # i.e. the mismatch could be a within-group row-order divergence
    # (ticket 21) rather than a genuine content difference. Diagnostic only;
    # never suppresses a mismatch, only informs its classification.
    row_order_candidate: bool = False


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
    r_df: pl.DataFrame,
    py_df: pl.DataFrame,
    key_cols: list[str],
    order_group_cols: list[str] | None = None,
) -> list[CellMismatch]:
    """Diff matched rows cell-by-cell.

    ``order_group_cols`` (ticket 21) opts into an extra diagnostic: for a
    positional row-alignment key (``add_row_ordinal``'s ``__row_ordinal``,
    not a real identity key), a within-group sort-order divergence between R
    and Python -- e.g. R falling back to raw input order when
    ``product_entry_date`` fails to parse, while Python sorts chronologically
    -- produces a cascade of cell mismatches that are really the *same*
    value landing on a different row, not a content difference. Per column,
    each mismatched cell is checked against a multiset of the Python side's
    own values across its whole ``order_group_cols`` group (not just
    adjacent rows, since a shift can be more than one position); a hit sets
    ``row_order_candidate`` for the classifier registry to act on. Omit
    ``order_group_cols`` for a genuine identity key (e.g. patient's
    ``patient_id`` + ``sheet_name``), where this check doesn't apply.
    """
    joined = r_df.join(py_df, on=key_cols, how="inner", suffix="_py")
    value_cols = [c for c in r_df.columns if c not in key_cols and c in py_df.columns]

    group_value_counts: dict[tuple[Any, ...], dict[str, Counter[Any]]] = {}
    if order_group_cols:
        for row in py_df.iter_rows(named=True):
            gkey = tuple(row[c] for c in order_group_cols)
            per_column = group_value_counts.setdefault(gkey, {})
            for col in value_cols:
                per_column.setdefault(col, Counter())[row[col]] += 1

    mismatches = []
    for row in joined.iter_rows(named=True):
        key = {k: row[k] for k in key_cols}
        gkey = tuple(row[c] for c in order_group_cols) if order_group_cols else None
        for col in value_cols:
            r_value, py_value = row[col], row[f"{col}_py"]
            if _values_differ(r_value, py_value):
                row_order_candidate = False
                if gkey is not None:
                    counts = group_value_counts.get(gkey, {}).get(col)
                    row_order_candidate = bool(counts) and counts[r_value] > 0
                mismatches.append(
                    CellMismatch(
                        key=key,
                        column=col,
                        r_value=r_value,
                        py_value=py_value,
                        row_order_candidate=row_order_candidate,
                    )
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


def _is_r_value_missing(m: CellMismatch) -> bool:
    """R produced null where Python has a real value.

    Named generically rather than "typo_rescue" (its original name): ticket 18
    found the R source has no forward-fill for this column and, separately,
    that R sometimes fails to extract a perfectly clean source value (see
    2018_Mahosot Hospital, Jan18) -- i.e. most cases in this bucket aren't
    typo-driven at all. classify() only sees the parsed (r_value, py_value)
    pair, not the raw source cell, so it can't distinguish a genuine
    source-typo rescue from a plain R extraction gap; both look identical
    here and are lumped together deliberately.
    """
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
    "r_value_missing": _is_r_value_missing,
    "ce_typo": _is_ce_typo,
    "off_by_one_day": _is_off_by_one_day,
}


def _is_r_category_lookup_miss(m: CellMismatch) -> bool:
    """R's add_product_categories (read_product_data.R) left-joins the raw
    product string against the category mapping with no normalization; a
    case or whitespace difference in the tracker's product name misses the
    join and leaves product_category null, while Python's reference/products.py
    lowercases and strips before matching. Verified via source read (ticket
    18), not just the data pattern -- a genuine R limitation, not a Python bug.
    """
    return m.r_value is None and m.py_value is not None


PRODUCT_CATEGORY_CLASSIFIERS: dict[str, Classifier] = {
    "r_category_lookup_miss": _is_r_category_lookup_miss,
}


def _is_row_order_divergence(m: CellMismatch) -> bool:
    """R's value for this cell shows up elsewhere in Python's own group.

    Root-caused (ticket 21) to R's per-(clinic, sheet) sort falling back to
    raw input order whenever ``product_entry_date`` fails to parse for a
    row -- itself the same R date-extraction gap ticket 18 already
    root-caused for the date column directly (see ``r_value_missing``).
    Python parses the date and sorts chronologically instead, so both sides
    land on the same total (e.g. same end-of-sheet balance) via a different
    per-row order -- not a genuine content divergence, and not something to
    "fix" toward R's order, since Python's is the one verified against the
    real source Excel dates.
    """
    return m.row_order_candidate


PRODUCT_ROW_ORDER_CLASSIFIERS: dict[str, Classifier] = {
    "row_order_divergence": _is_row_order_divergence,
}


def _is_r_extraction_gap(m: CellMismatch) -> bool:
    """R produced null where Python has a real value.

    Verified against the real source Excel (ticket 28): R's static
    "Patient List" recruitment-date extraction fails to populate
    recruitment_date for the large majority of patients even where the
    tracker plainly records one (e.g. Quirino Memorial Medical Center,
    patient PH_QD001, "Date of Recruitment" = 2025-12-01 in the source file --
    Python extracts it correctly, R leaves it null). A genuine R limitation,
    not a Python defect.
    """
    return m.r_value is None and m.py_value is not None


PATIENT_RECRUITMENT_DATE_CLASSIFIERS: dict[str, Classifier] = {
    "r_extraction_gap": _is_r_extraction_gap,
}


def _is_r_validator_rejects_multivalue(m: CellMismatch) -> bool:
    """R's own allowed-values validator rejects the multi-insulin CSV output
    R's own derivation logic produces for 2024+ trackers, replacing it with
    the "Undefined" sentinel -- confirmed in code (src/a4d/clean/patient.py's
    _derive_insulin_fields docstring, ticket 28): Python's derivation is a
    deliberate, documented correction of an R typo and validator bug, not a
    parity gap to close.
    """
    return m.r_value == "Undefined" and m.py_value is not None


PATIENT_INSULIN_SUBTYPE_CLASSIFIERS: dict[str, Classifier] = {
    "r_validator_rejects_multivalue": _is_r_validator_rejects_multivalue,
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
    order_group_cols: list[str] | None = None,
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
                cell_mismatches=compare_cells(r_df, py_df, key_cols, order_group_cols),
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
    column_divergence_rows = []

    for file_comparison in comparison.files:
        name = file_comparison.file_name

        for column in file_comparison.columns.only_in_r:
            column_divergence_rows.append(
                {"file": name, "column": column, "kind": "only in R", "r_dtype": "", "py_dtype": ""}
            )
        for column in file_comparison.columns.only_in_py:
            column_divergence_rows.append(
                {
                    "file": name,
                    "column": column,
                    "kind": "only in Python",
                    "r_dtype": "",
                    "py_dtype": "",
                }
            )
        for column, r_dtype, py_dtype in file_comparison.columns.dtype_mismatches:
            column_divergence_rows.append(
                {
                    "file": name,
                    "column": column,
                    "kind": "dtype mismatch",
                    "r_dtype": str(r_dtype),
                    "py_dtype": str(py_dtype),
                }
            )

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
        "column_divergence": column_divergence_rows,
        "id_overlap": id_overlap_rows,
        "categorical_overlap": categorical_overlap_rows,
        "row_key_overlap": row_key_overlap_rows,
        "totals": totals_rows,
        "cell_mismatches": cell_mismatch_rows,
    }


def snapshot_from_summary(summary: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, int]]:
    """Reduce a ``build_summary_rows`` result to a compact, JSON-serializable
    snapshot for run-over-run history (ticket 19).

    Only ``per_column``/``per_cause`` are kept -- the counts that actually
    move as triage fixes land -- keyed as plain strings so the snapshot
    round-trips through JSON without a custom decoder.
    """
    per_column = {row["column"]: row["mismatches"] for row in summary.get("per_column", [])}
    per_cause = {
        f"{row['column']}|{row['cause']}": row["mismatches"] for row in summary.get("per_cause", [])
    }
    return {"per_column": per_column, "per_cause": per_cause}


@dataclass(frozen=True)
class Delta:
    key: str
    previous: int
    current: int


def compute_deltas(previous: dict[str, int], current: dict[str, int]) -> list[Delta]:
    """Diff two snapshot count-dicts, keyed by column or "column|cause".

    Only changed keys are returned -- a key with an unchanged count (present
    identically in both, or absent from both) is not a fix or a regression
    and would just be noise in a delta report. A key missing from one side
    is treated as a count of 0 on that side, so a fully-resolved column
    (count drops to zero and the row disappears from the new summary) still
    shows up as a delta rather than silently vanishing.
    """
    keys = previous.keys() | current.keys()
    return sorted(
        (
            Delta(key=key, previous=previous.get(key, 0), current=current.get(key, 0))
            for key in keys
            if previous.get(key, 0) != current.get(key, 0)
        ),
        key=lambda d: d.key,
    )


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
