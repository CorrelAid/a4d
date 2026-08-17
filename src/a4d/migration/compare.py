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
import itertools
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from a4d.clean.date_parser import parse_date_flexible
from a4d.clean.glucose import (
    GLUCOSE_COLUMNS as GLUCOSE_UNIT_COLUMNS,
)
from a4d.clean.glucose import (
    MG_ANALYTICAL_MAX,
    MG_ANALYTICAL_MIN,
    MMOL_ANALYTICAL_MAX,
    MMOL_ANALYTICAL_MIN,
    MMOL_TO_MG_FACTOR,
)
from a4d.clean.validators import load_validation_rules, sanitize_str
from a4d.config import settings

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
        except TypeError, ValueError:
            return value

    parsed = [_try_float(v) for v in df[column]]
    return df.with_columns(pl.Series(column, parsed, dtype=pl.Object))


def numeric_normalize_targets(df: pl.DataFrame, exclude: Sequence[str]) -> list[str]:
    """Raw-stage columns to parse back to ``float`` before diffing.

    The cleaned schema is the wrong source for this list even though it is
    derived rather than hand-written: it has no entry at all for the Patient
    List join's ``.static`` copies, and it types a screening measurement as a
    string because the same column can also hold "normal". Both still carry
    plain floats whose string forms R and Python round differently, so both
    were reported as mismatches. Since the raw stage stores every value as
    text and ``normalize_numeric_column`` leaves non-numeric text untouched,
    the correct scope is every column except the ones the row-alignment join
    must keep as text.
    """
    excluded = set(exclude)
    return [c for c in df.columns if c not in excluded and not c.startswith("__")]


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


# Name of the positional row-alignment column add_row_ordinal creates.
ROW_ORDINAL_COL = "__row_ordinal"


def add_row_ordinal(
    df: pl.DataFrame, group_cols: list[str], ordinal_col: str = ROW_ORDINAL_COL
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


# A duplicate group is brute-forced over all pairings, so it is bounded. The
# real data's largest two-sided patient duplicate group is 4 rows (2023_NPH);
# anything beyond this keeps positional pairing rather than costing 5040+
# permutations for a group that is almost certainly a source defect of a
# different kind.
MAX_DUPLICATE_GROUP_FOR_MATCHING = 6


def _pairing_cost(
    r_df: pl.DataFrame, py_df: pl.DataFrame, value_cols: list[str], pairs: Sequence[tuple[int, int]]
) -> int:
    return sum(
        1
        for r_index, py_index in pairs
        for col in value_cols
        if _values_differ(r_df[col][r_index], py_df[col][py_index])
    )


def align_duplicate_rows(
    r_df: pl.DataFrame, py_df: pl.DataFrame, group_cols: list[str]
) -> tuple[pl.DataFrame, pl.DataFrame, list[str]]:
    """Align two frames on an identity key, breaking ties by content (ticket 45).

    ``add_row_ordinal`` alone makes a repeated identity key unique again, but
    it does so by *position*, which assumes both sides emit a duplicated
    patient's rows in the same order. They do at the raw stage and demonstrably
    do not at the cleaned stage, where a positional tie-break pairs the wrong
    two copies of the same patient and reports every differing column twice
    over.

    Within a patient-and-sheet group the row order carries no meaning, so
    duplicates are paired to minimise the number of differing cells --
    brute-forced, since such groups are tiny and rare (24 groups in 5 of 250+
    files). Position is kept unless some other pairing is *strictly* better, so
    a group whose rows genuinely both changed is never permuted into looking
    like agreement. Groups present on only one side, or larger than
    ``MAX_DUPLICATE_GROUP_FOR_MATCHING``, keep positional order.
    """
    r_keyed, key_cols = add_row_ordinal(r_df, group_cols)
    py_keyed, _ = add_row_ordinal(py_df, group_cols)
    group_key_cols = key_cols[:-1]
    value_cols = [c for c in r_df.columns if c in py_df.columns and c not in group_cols]

    def _rows_by_group(df: pl.DataFrame) -> dict[tuple[Any, ...], list[int]]:
        groups: dict[tuple[Any, ...], list[int]] = {}
        for index, row in enumerate(df.select(group_key_cols).iter_rows()):
            groups.setdefault(row, []).append(index)
        return groups

    r_groups, py_groups = _rows_by_group(r_keyed), _rows_by_group(py_keyed)
    py_ordinals = py_keyed[ROW_ORDINAL_COL].to_list()

    for group, r_indices in r_groups.items():
        py_indices = py_groups.get(group, [])
        if len(r_indices) < 2 or len(r_indices) != len(py_indices):
            continue
        if len(r_indices) > MAX_DUPLICATE_GROUP_FOR_MATCHING:
            continue
        positional = list(zip(r_indices, py_indices, strict=True))
        best_cost = _pairing_cost(r_keyed, py_keyed, value_cols, positional)
        best: Sequence[tuple[int, int]] = positional
        for permutation in itertools.permutations(py_indices):
            candidate = list(zip(r_indices, permutation, strict=True))
            cost = _pairing_cost(r_keyed, py_keyed, value_cols, candidate)
            if cost < best_cost:
                best_cost, best = cost, candidate
        for ordinal, (_, py_index) in enumerate(best):
            py_ordinals[py_index] = ordinal

    py_keyed = py_keyed.with_columns(pl.Series(ROW_ORDINAL_COL, py_ordinals))
    return r_keyed, py_keyed, key_cols


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
    # Set by compare_cells when order_group_cols is given and the key is
    # positional: True if this column's value on the group's LAST row agrees
    # on both sides. For a derived running total (product_balance), which is
    # recomputed per row and so cannot travel with its row under a re-sort,
    # this is the order-independent evidence row_order_candidate cannot
    # supply -- the ledgers took different paths to the same closing figure
    # (ticket 36). Diagnostic only, like row_order_candidate.
    group_endpoint_matches: bool = False


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

    group_endpoint_agrees = _group_endpoint_agreement(
        joined, order_group_cols, key_cols, value_cols
    )

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
                        group_endpoint_matches=group_endpoint_agrees.get((gkey, col), False),
                    )
                )
    return mismatches


def _group_endpoint_agreement(
    joined: pl.DataFrame,
    order_group_cols: list[str] | None,
    key_cols: list[str],
    value_cols: list[str],
) -> dict[tuple[Any, str], bool]:
    """Per (group, column): does the group's last positional row agree?

    Only meaningful for ``add_row_ordinal``'s positional key, so it is keyed
    off ``ROW_ORDINAL_COL`` being present rather than off a new parameter --
    a genuine identity key has no "last row" to speak of.
    """
    if not order_group_cols or ROW_ORDINAL_COL not in key_cols:
        return {}

    last_ordinals: dict[tuple[Any, ...], int] = {}
    for row in joined.iter_rows(named=True):
        gkey = tuple(row[c] for c in order_group_cols)
        ordinal = row[ROW_ORDINAL_COL]
        if ordinal > last_ordinals.get(gkey, -1):
            last_ordinals[gkey] = ordinal

    agreement: dict[tuple[Any, str], bool] = {}
    for row in joined.iter_rows(named=True):
        gkey = tuple(row[c] for c in order_group_cols)
        if row[ROW_ORDINAL_COL] != last_ordinals[gkey]:
            continue
        for col in value_cols:
            agreement[(gkey, col)] = not _values_differ(row[col], row[f"{col}_py"])
    return agreement


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


def _is_python_future_date_sentinel(m: CellMismatch) -> bool:
    """Python replaced an out-of-tracker-year date with R's own error sentinel.

    ``_validate_entry_dates`` (clean/product.py) and its patient counterpart
    ``_validate_dates`` (clean/patient.py) log a parsed date whose year is
    beyond the tracker's own calendar year and substitute
    ``error_val_date`` (9999-09-09), because a future date is genuinely
    ambiguous -- a premature next-month entry or a typo -- and the sentinel
    preserves that signal. R validates nothing and carries the bad date
    through. Verified against the real source data (ticket 36): for Preah
    Kossamak's 2023 tracker, sheet Aug23, *both* pipelines independently read
    2029-08-29 out of a sheet whose every other row is August 2023, so the
    source really does hold the typo -- Python flags it, R propagates it.
    """
    return m.py_value == SENTINEL_DATE and isinstance(m.r_value, datetime.date)


# An entry-date cell parsing to 1900 is not a date the clinician wrote: it is
# a tiny integer (a stray day-of-month, e.g. "30") landing in the date column
# on an end-of-block summary row and being read as an Excel serial.
_SUMMARY_RESIDUE_YEAR = 1900


def _is_summary_residue_nulled(m: CellMismatch) -> bool:
    """Python nulled end-of-block summary-row residue that R kept as a date.

    ``PRODUCT_DATE_NA_MARKERS`` and the tiny-int scrub (clean/product.py)
    null these before parsing, so the cleaned output is NULL rather than
    1900-01-30. Python is the correct side: 1900-01-30 is not a date any
    tracker records.
    """
    return (
        m.py_value is None
        and isinstance(m.r_value, datetime.date)
        and m.r_value.year <= _SUMMARY_RESIDUE_YEAR
    )


PRODUCT_ENTRY_DATE_CLASSIFIERS: dict[str, Classifier] = {
    "sentinel_null": _is_sentinel_null,
    "r_value_missing": _is_r_value_missing,
    "ce_typo": _is_ce_typo,
    "off_by_one_day": _is_off_by_one_day,
    "python_future_date_sentinel": _is_python_future_date_sentinel,
    "summary_residue_nulled": _is_summary_residue_nulled,
}

# The patient arm's cleaned stage runs the same future-date guard, so its date
# columns need the same cause without the product-specific siblings above.
PATIENT_FUTURE_DATE_CLASSIFIERS: dict[str, Classifier] = {
    "python_future_date_sentinel": _is_python_future_date_sentinel,
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


def _is_derived_running_total_row_order(m: CellMismatch) -> bool:
    """Two ledgers, different accumulation order, same closing figure.

    ``product_balance`` is recomputed per row on both sides
    (``_compute_running_balance``, step 2.15, mirroring R's
    ``compute_balance``), so under the sort-order divergence ticket 21
    root-caused it cannot travel with its row -- Python's intermediate
    balances are a chronological ledger, R's a data-entry-order one, and
    neither side's intermediate values appear in the other's group. Value
    membership therefore cannot detect it in principle; the group's *closing*
    balance can, being order-independent.

    Measured across the real 248-tracker pair (ticket 36): 2,729 of the 2,740
    mismatching balance cells sit in groups whose closing balance agrees
    exactly (2,281 of 2,283 groups). The 11 that do not are deliberately left
    unclassified -- see the ticket: both are 2019 Sultanah Bahiyah groups
    where R's ledger is corrupted by an Excel date serial leaking out of
    "Units Received", so a disagreeing endpoint is a real signal worth
    surfacing rather than a label to absorb it.
    """
    return m.group_endpoint_matches


DERIVED_RUNNING_TOTAL_CLASSIFIERS: dict[str, Classifier] = {
    "derived_running_total_row_order": _is_derived_running_total_row_order,
}


# Product rows are aligned by ordinal position within (clinic_id,
# product_sheet_name), so a within-group re-sort can move any column's value
# to a different row -- except these, which hold the same value for every row
# of a group and therefore cannot diverge by ordering alone. Everything else
# in the product schema must carry PRODUCT_ROW_ORDER_CLASSIFIERS; ticket 36's
# wiring test derives that list from this exclusion rather than restating it.
GROUP_INVARIANT_PRODUCT_COLUMNS = frozenset(
    {
        "clinic_id",  # alignment group key
        "product_sheet_name",  # alignment group key
        "file_name",  # one value per compared file
        "product_table_month",  # derived from the sheet, so constant per group
        "product_table_year",
    }
)


def _is_r_extraction_gap(m: CellMismatch) -> bool:
    """R produced null where Python has a real value.

    Three source-verified instances share this shape, in three different
    tracker generations. classify() sees only the (r_value, py_value) pair,
    not the file, so they carry one cause name; the mechanisms are:

    - ``recruitment_date`` (ticket 28): R's static "Patient List"
      recruitment-date extraction fails to populate it for the large majority
      of patients even where the tracker plainly records one (e.g. Quirino
      Memorial Medical Center, patient PH_QD001, "Date of Recruitment" =
      2025-12-01 in the source).
    - ``edu_occ_updated`` on 2022 trackers (ticket 37): R's own
      "Updated 2022" header fixup (script1_helper_read_patient_data.R)
      rewrites that cell to "Level of Education Or Occupation", but the
      source cell reads " Updated \\n2022" with a *leading* space, which
      survives the rewrite -- so R's merged header is " Level of Education Or
      Occupation Date" and R's name sanitizer turns it into the junk column
      ``xlevelofeducationoroccupationdate``, which no synonym matches. The
      same fixup's blood-pressure branch has no leading space and works.
      Verified against the real source Excel (2022 Kantha Bopha, Patient
      List!M13/N13: "Law School - Year 2" updated 2022-11-04) and against R's
      own raw parquet, which carries the junk column.
    - ``blood_pressure_updated`` and ``edu_occ_updated`` on 2026 trackers
      (ticket 37): the 2026 template moved the complication-screening block
      to a new "Annual" sheet; R reads no values from it at all (0 non-null
      for the whole file), while Python extracts them. Verified against the
      real source Excel (06 YGH T1D Tracker_June_26, Annual!G/H/I for
      MM_QF101: 2026-02-05, 100, 60).

    A genuine R limitation in every case, not a Python defect.
    """
    return m.r_value is None and m.py_value is not None


PATIENT_R_EXTRACTION_GAP_CLASSIFIERS: dict[str, Classifier] = {
    "r_extraction_gap": _is_r_extraction_gap,
}


def _is_r_insulin_dedup_drop(m: CellMismatch) -> bool:
    """R deletes the whole "TOTAL Insulin Units" column before it is ever read.

    ``extract_patient_data`` (r-archive/R/script1_helper_read_patient_data.R)
    carries a hack for a merged-cell artefact that can produce two "insulin
    regimen" columns: it greps the source headers for the literal ``Insulin``
    and drops every match after the first. Since the 2024 tracker redesign the
    monthly sheet also carries "TOTAL Insulin Units per day", so that grep
    matches two real, unrelated columns and the hack deletes the second. The
    sibling insulin columns survive only because their sub-headers read
    "Pre-mixed"/"Short-acting" (the "Human Insulin" group header sits in a row
    R does not merge here) and "Number of insulin injections" has a lowercase
    "i" the case-sensitive grep misses.

    Verified against the real source Excel (ticket 29, 06 500 NPT Children's
    Hospital, Jan26!AA94-98: 20, 48, 24, 30, 20 -- exactly Python's values):
    the column is absent from R's raw output entirely, so R's cleaned-stage
    template leaves it null on all 81,859 rows. Python is not diverging, it is
    the only side that reads the column at all.
    """
    return m.r_value is None and m.py_value is not None


PATIENT_INSULIN_TOTAL_UNITS_CLASSIFIERS: dict[str, Classifier] = {
    "r_insulin_dedup_drop": _is_r_insulin_dedup_drop,
}


def _is_r_join_suffix_collision(m: CellMismatch) -> bool:
    """R's Patient List join renames *both* sides on a name collision.

    ``reading_patient_data`` (r-archive/R/script1_read_patient_data.R) joins
    the monthly sheets to the static "Patient List" sheet with
    ``suffix = c(".monthly", ".static")``. Where a column exists on both
    sheets, dplyr renames both, so the unsuffixed name disappears -- and R's
    cleaning stage, which reads ``fbg_baseline_mg``, then finds nothing and
    leaves the schema column null for the whole file. R avoids this for
    ``hba1c_baseline`` by explicitly dropping the monthly copy before the
    join; it never does the same for the baseline FBG columns.

    Polars suffixes only the right-hand frame, so Python keeps the monthly
    value under the base name and the Patient List copy as ``.static``.
    Measured against the real drive data (ticket 29): 21 files collide on
    ``fbg_baseline_mg`` and 3 on ``fbg_baseline_mmol``, and across their
    ~10,000 rows the two copies are identical or numerically equal in 92.4%,
    so the column Python keeps is very nearly the one R lost. The 663 rows
    where the two sheets genuinely disagree are the source contradicting
    itself, not a pipeline choice either side can resolve.
    """
    return m.r_value is None and m.py_value is not None


PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS: dict[str, Classifier] = {
    "r_join_suffix_collision": _is_r_join_suffix_collision,
}


def _is_r_numeric_error_sentinel(m: CellMismatch) -> bool:
    """R stamps 999999 on a cell that never held a usable number; Python nulls it.

    R has no missing-value normalization before ``as.numeric()``, so a
    clinician's "-", "NA" or free text ("2 months") fails to parse and R's
    cleaning substitutes ``ERROR_VAL_NUMERIC`` (999999).
    ``safe_convert_column`` (src/a4d/clean/converters.py) normalizes those
    markers to null *before* conversion, deliberately: 999999 means "a value
    was recorded but is invalid", which is the wrong claim for a blank, and a
    magic number silently poisons every downstream mean.

    Checked exhaustively, not sampled (ticket 29): all 8,085 rows carrying
    this shape were traced back to Python's own raw stage, and **not one** had
    a clean number behind it. 3,530 are missing-value markers, 2,331 are Excel
    formula-error strings, 1,719 are unparseable free text; 505 could not be
    joined back to a raw row. No data is lost on Python's side -- the
    information R keeps is the fact of a failed parse, which Python records in
    the error log instead of in the data.
    """
    if m.py_value is not None or m.r_value is None:
        return False
    try:
        # The sentinel reaches here as a float from a numeric column and as
        # text from a string-typed one, so compare numerically either way.
        return float(m.r_value) == settings.error_val_numeric  # type: ignore[arg-type]
    except TypeError, ValueError:
        return False


R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS: dict[str, Classifier] = {
    "r_numeric_error_sentinel": _is_r_numeric_error_sentinel,
}


def _as_date(value: Any) -> datetime.date | None:
    """The date behind a cell value, whether it arrives as a date or a datetime.

    A ``pl.Date`` column reads back as ``date`` and a ``pl.Datetime`` one as
    ``datetime``; ``datetime`` is a subclass of ``date`` but never equal to it,
    so a plain ``==`` against the sentinel silently misses half the cases.
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    return value if isinstance(value, datetime.date) else None


def _is_r_date_error_sentinel(m: CellMismatch) -> bool:
    """R stamps 9999-09-09 on a date cell that recorded an absence; Python nulls it.

    The date-column twin of ``r_numeric_error_sentinel``. R's ``parse_dates``
    (script2_helper_patient_data_fix.R) tests ``is.na(date)``, which is false
    for the *string* "NA", so the value falls through to ``lubridate::as_date``,
    fails, and ``convert_to`` substitutes ``ERROR_VAL_DATE``.

    Python is the correct side, and the source says so explicitly: the tracker
    template's own sub-header for ``hospitalisation_date`` reads "(Insert Date
    or NA)", so a cell holding "NA" is the form being filled in as designed,
    not a date that failed to parse. Verified on the real 254-tracker set
    (ticket 38): of the 1,607 cells carrying this shape, 1,565 were traced back
    to a raw value both pipelines agree on -- literal "NA" -- with the
    remainder unmatched to a raw row rather than contradicting it. Checked
    directly in the source workbook for 2020 Mahosot (Jan20, column 24, header
    "Hospitalisation due to diabetes emergency or glucose control / (Insert
    Date or NA)"), where "NA" is what the clinic wrote on nearly every row.

    Ticket 38 also widened Python's own missing-marker set on the date path
    (``MISSING_VALUE_MARKERS`` / ``DATE_ABSENCE_MARKERS``, clean/date_parser.py),
    so cells recording absence as "-", "Nil", "Unknown" or the template's
    leftover placeholder text now land here too rather than agreeing with R's
    sentinel by accident.
    """
    return m.py_value is None and m.r_value is not None and _as_date(m.r_value) == SENTINEL_DATE


R_DATE_ERROR_SENTINEL_CLASSIFIERS: dict[str, Classifier] = {
    "r_date_error_sentinel": _is_r_date_error_sentinel,
}


def _declared_aliases() -> dict[str, set[str]]:
    """Canonical label -> the sanitized retired spellings it absorbs.

    Read from ``reference_data/validation_rules.yaml`` rather than restated
    here, so this classifier cannot drift from the config that produced the
    values it is explaining.
    """
    resolved: dict[str, set[str]] = {}
    for spec in load_validation_rules().values():
        if not isinstance(spec, dict):
            continue
        for canonical, spellings in (spec.get("aliases") or {}).items():
            resolved.setdefault(canonical, set()).update(sanitize_str(s) for s in spellings)
    return resolved


ALIAS_CANONICAL_LABELS = _declared_aliases()


def _is_python_canonical_label(m: CellMismatch) -> bool:
    """R emits a retired spelling of a label; Python emits the canonical one.

    Where a tracker generation renamed a status, both spellings appear across
    the corpus -- "Active - Remote" in 2020-2023 trackers, "Active Remote" in
    2024+ ones, which is the only spelling the Lookup List dropdown
    introduced with the 2024 template defines (verified against the real
    source workbooks, ticket 29). R's own config lists both as allowed values
    and R's first-match lookup collapses everything onto the older spelling.
    Python declares one canonical label per status and folds the retired
    spellings into it, so the reports carry one label per status rather than
    two competing ones. A deliberate divergence from the frozen R baseline,
    not a defect on either side -- and the source cell is unchanged in both.
    """
    if not isinstance(m.r_value, str) or not isinstance(m.py_value, str):
        return False
    return sanitize_str(m.r_value) in ALIAS_CANONICAL_LABELS.get(m.py_value, set())


PYTHON_CANONICAL_LABEL_CLASSIFIERS: dict[str, Classifier] = {
    "python_canonical_label": _is_python_canonical_label,
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


def _is_r_validator_rejects_untrimmed(m: CellMismatch) -> bool:
    """R's allowed-value validator rejected a value for its whitespace alone.

    readxl does not trim these patient cells, so a source value like "F " (a
    real one -- Kantha Bopha 2019, patient KH_QD023, verified in the source
    Excel) misses R's allowed-value list and lands on the "Undefined"
    character sentinel. Python's cleaning strips string cells before
    validation (ticket 36), so it keeps the value. Python is recovering data
    both pipelines previously lost, not diverging.
    """
    return m.r_value == "Undefined" and m.py_value is not None


PATIENT_UNTRIMMED_VALIDATION_CLASSIFIERS: dict[str, Classifier] = {
    "r_validator_rejects_untrimmed": _is_r_validator_rejects_untrimmed,
}


PATIENT_INSULIN_SUBTYPE_CLASSIFIERS: dict[str, Classifier] = {
    "r_validator_rejects_multivalue": _is_r_validator_rejects_multivalue,
}


def _is_r_ifelse_na_propagation(m: CellMismatch) -> bool:
    """R's derivation returns NA because one input is NA, not because the
    answer is unknown.

    ``insulin_type`` is derived on both sides from the five 2024+ insulin
    columns. R (script2_process_patient_data.R:94) writes
    ``ifelse(pre_mixed == "Y" | short_acting == "Y" | intermediate == "Y",
    "human insulin", "analog insulin")``. Under R's three-valued logic
    ``FALSE | FALSE | NA`` is NA, so a row whose human columns are blank --
    but whose *analog* columns plainly read "Y" -- yields NA and R loses the
    type entirely. ``_derive_insulin_fields`` (clean/patient.py) instead
    derives whenever any of the five columns is populated, so it answers
    "analog insulin" for exactly those rows.

    Verified against the real 248-tracker pair (ticket 37, 06 Baguio General
    Hospital_Jun_26, May26, PH_QA001 and PH_QA004): both pipelines hold the
    *same* five input values (human blank/N, rapid-acting Y, long-acting Y),
    R's insulin_type is NULL and Python's is "Analog Insulin". Python is the
    correct side -- the information is in the row, R's NA propagation drops
    it. Not the same cause as ``r_validator_rejects_multivalue`` on the
    sibling ``insulin_subtype`` column, which is a validator rejection of a
    value R did produce.
    """
    return m.r_value is None and m.py_value is not None


PATIENT_INSULIN_TYPE_CLASSIFIERS: dict[str, Classifier] = {
    "r_ifelse_na_propagation": _is_r_ifelse_na_propagation,
}


def _excel_serial_to_datetime(serial: float) -> datetime.date | datetime.time | datetime.datetime:
    """Convert an Excel serial to the exact value openpyxl would read for it.

    Delegates to openpyxl's own ``from_excel`` rather than hand-rolling the
    epoch math, for two reasons verified against real flagged rows (ticket
    24): Excel (and Lotus 1-2-3 before it) treats 1900 as a leap year that
    never existed, so serials 59 and 60 both resolve to 1900-02-28 -- a
    plain ``EXCEL_EPOCH + timedelta`` (this module's own
    ``parse_date_flexible`` convention) lands one day off for any serial in
    that range; and a serial with no whole-day component (e.g. 0) comes back
    as a bare ``datetime.time``, matching what openpyxl itself returns for a
    cell formatted as time-of-day only.
    """
    from openpyxl.utils.datetime import from_excel

    return from_excel(serial)


def _is_openpyxl_date_typed_stray_cell(m: CellMismatch) -> bool:
    """A numeric-typed column (raw ``product_units_received``/``product_received_from``)
    holds a lone Excel date/time-formatted cell.

    R's readxl infers a whole column's type from its majority values, so a
    stray date/time-formatted cell in an otherwise-numeric column still gets
    coerced to that column's numeric type -- the raw Excel serial. Python's
    openpyxl reads each cell individually and honors its own format instead,
    returning a ``datetime``/``time`` object. Verified against the real
    source Excel (ticket 24): the underlying cell genuinely carries a
    date/time number format (e.g. Penang General Hospital 2019 Apr19!E36,
    "Units Received" column, formatted ``d/m/yy``) -- Python's value is the
    faithful one, R's is a column-wide coercion artifact.
    """
    try:
        r_serial = float(m.r_value)
    except TypeError, ValueError:
        return False
    expected = _excel_serial_to_datetime(r_serial)
    if isinstance(expected, datetime.datetime):
        expected_date, expected_time = expected.date(), expected.time()
    elif isinstance(expected, datetime.date):
        expected_date, expected_time = expected, datetime.time(0, 0)
    else:
        expected_date, expected_time = None, expected
    py_str = str(m.py_value).strip()
    try:
        parsed = datetime.datetime.strptime(py_str, "%Y-%m-%d %H:%M:%S")
        return parsed.date() == expected_date and parsed.time() == expected_time
    except ValueError:
        pass
    try:
        parsed_time = datetime.datetime.strptime(py_str, "%H:%M:%S").time()
        return parsed_time == expected_time
    except ValueError:
        return False


STRAY_DATE_CLASSIFIERS: dict[str, Classifier] = {
    "openpyxl_date_typed_stray_cell": _is_openpyxl_date_typed_stray_cell,
}


# An Excel serial in the range a real 2000-2050 date occupies. A unit count
# this large does not occur in the tracker data (the largest genuine
# product_units_received across the 248-tracker set is three digits), so a
# value here is a misplaced date, not a quantity.
_PLAUSIBLE_DATE_SERIAL_RANGE = (36526.0, 54789.0)


def _is_stray_date_zeroed(m: CellMismatch) -> bool:
    """The cleaned-stage face of STRAY_DATE_CLASSIFIERS' cause (ticket 36).

    Where a clinician typed a date into a quantity column -- verified against
    the real source Excel (2019 Sultanah Bahiyah, Aug19 rows 10-12: the entry
    date sits in column E, "Units Received", with column D, "Date", empty) --
    R's readxl coerces the column to numeric and carries the raw serial into
    its output, corrupting the ledger it feeds (ticket 36's addendum measured
    R closing at 43,572 in five such groups). Python's cleaning fails the
    float cast, emits a ``type_conversion`` error per row, and zeroes the
    cell. Python is the correct side; the raw-stage classifier cannot see
    this because it expects Python's value to still be a datetime.
    """
    try:
        r_serial = float(m.r_value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return False
    low, high = _PLAUSIBLE_DATE_SERIAL_RANGE
    if not low <= r_serial <= high:
        return False
    try:
        return float(m.py_value) == 0.0  # type: ignore[arg-type]
    except TypeError, ValueError:
        return False


STRAY_DATE_ZEROED_CLASSIFIERS: dict[str, Classifier] = {
    "stray_date_zeroed": _is_stray_date_zeroed,
}


# Excel's own formula-error sentinels (ticket 27): a computed raw column
# (e.g. bmi, t1d_diagnosis_age -- both formula-derived in the source
# trackers) holds a literal "#DIV/0!"/"#VALUE!"/etc. string wherever the
# source formula could not compute -- an input it depends on was never
# recorded (height blank -> #DIV/0!; no diagnosis date -> #NUM!). Verified
# against real source Excel: the cell's openpyxl data_type is 'e'.
#
# Python's raw extraction preserves that text uniformly (ticket 27's own
# change -- the raw layer records what the source contained). R's does not:
# readxl guesses a column's type from its majority values, so the same error
# cell survives as a string in a column guessed character but becomes NA in
# a column guessed numeric -- the same type-guessing mechanism
# STRAY_DATE_CLASSIFIERS documents for a different symptom. So the mismatch
# appears in BOTH directions depending on which way readxl guessed, and
# neither direction is a Python defect: Python is the consistent side.
EXCEL_ERROR_STRINGS = frozenset(
    {"#DIV/0!", "#VALUE!", "#NUM!", "#N/A", "#REF!", "#NAME?", "#NULL!"}
)


def _is_excel_formula_error(m: CellMismatch) -> bool:
    return (m.r_value in EXCEL_ERROR_STRINGS and m.py_value is None) or (
        m.py_value in EXCEL_ERROR_STRINGS and m.r_value is None
    )


EXCEL_FORMULA_ERROR_CLASSIFIERS: dict[str, Classifier] = {
    "excel_formula_error": _is_excel_formula_error,
}


# Buddhist-era source-data typo (ticket 27): a clinician typed a Thai
# Buddhist-Era year (BE = CE + 543) directly into a Gregorian-calendar
# date cell -- verified against the real source Excel (06 Nakornping
# Hospital, patient TH_QF004, hba1c_updated_date: the cell is genuinely
# date-typed and formatted `dd-mmm-yyyy` but holds year 2569). R's raw
# extraction already rejects the implausible year and emits the sentinel;
# Python's raw extraction is a faithful pass-through of the cell's literal
# value, by design, so it carries the bad year through. Not a pipeline bug:
# the cleaned stage's own future-date guard (`_validate_dates`,
# `clean/patient.py`) independently replaces it with the same sentinel.
#
# Which side sentinels is not fixed (ticket 37): on `blood_pressure_updated`
# the direction reverses at the cleaned stage, because R's raw extraction
# carries the BE year through for that column and R's cleaning has no
# future-date guard, while Python's does. Same typo, same verdict -- the
# sentinelling side is the one that recognized an unusable year -- so the
# test is symmetric rather than two separately-named causes. Threshold
# matches the product pipeline's own `BUDDHIST_ERA_THRESHOLD`
# (`clean/product.py`) rather than a new one.
PATIENT_BUDDHIST_ERA_THRESHOLD = 2400


def _is_buddhist_era_typo(m: CellMismatch) -> bool:
    sentinelled, carried = (
        (m.r_value, m.py_value) if m.r_value == SENTINEL_DATE else (m.py_value, m.r_value)
    )
    return (
        sentinelled == SENTINEL_DATE
        and isinstance(carried, datetime.date)
        and carried.year >= PATIENT_BUDDHIST_ERA_THRESHOLD
    )


PATIENT_BUDDHIST_ERA_CLASSIFIERS: dict[str, Classifier] = {
    "buddhist_era_typo": _is_buddhist_era_typo,
}


def _is_r_na_unite_padding(m: CellMismatch) -> bool:
    """R renders an absent sub-column as the literal string ``NA`` when uniting.

    The 2023 template splits complication screening across B.P./Kidney/Eye/Foot/
    Lipids sub-columns that all map to one canonical ``complication_screening``;
    ``reading_patient_data`` (r-archive/R/script1_read_patient_data.R) merges them
    with ``tidyr::unite(sep = ",")``, whose ``na.rm`` defaults to ``FALSE``, so
    every empty cell in the group becomes the four characters ``NA`` in R's
    output: a patient screened in January reads ``JAN,NA,NA,NA,NA`` and a patient
    screened not at all reads ``NA,NA,NA,NA,NA`` rather than being null.

    Python merges the same group in ``ColumnMapper.rename_columns`` but skips
    empty cells, so it carries the values alone. Verified against the real source
    Excel (2023 Kantha Bopha, Jan'23!AB98-AF98 = B.P./Kidney/Eye/Foot/Lipids;
    KH_QD023 has ``JAN`` in Kidney and nothing else): the sub-columns R pads are
    genuinely empty in the workbook, so the padding is R's rendering and carries
    no information. Python is the correct side.

    Fires only when stripping the ``NA`` tokens from R's value leaves exactly
    Python's value, so a real disagreement inside the group stays unclassified.
    """
    if m.r_value is None or "NA" not in str(m.r_value):
        return False
    stripped = [p for p in str(m.r_value).split(",") if p.strip() not in ("NA", "")]
    py_parts = [] if m.py_value is None else str(m.py_value).split(",")
    return stripped == [p for p in py_parts if p.strip() != ""]


PATIENT_NA_UNITE_PADDING_CLASSIFIERS: dict[str, Classifier] = {
    "r_na_unite_padding": _is_r_na_unite_padding,
}


def _glucose_float(value: Any) -> float | None:
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _is_python_glucose_unit_corrected(m: CellMismatch) -> bool:
    """Python resolves a glucose reading recorded under the wrong unit's header;
    R carries the number through as written.

    Ticket 42, on A4D's medical advisor's answer of 2026-08-17. Where a whole
    column labelled mg/dL holds mmol/L readings (measured: 29 file-columns at 21
    clinics, nine tenths or more of each column below 30 mg/dL),
    ``resolve_glucose_units`` (src/a4d/clean/glucose.py) moves the values to the
    mmol column and rescales the mg one by 18. It also blanks readings of exactly
    0, which sit below the analytical floor of both units and mean "not
    measured", and range validation then rejects readings outside the advisor's
    analytical limits. R has no unit resolution at all, so each of those shows as
    a divergence.

    This is a **deliberate Python correction, not an R defect and not a
    divergence either side could win** -- R was never asked the question. It
    fires only on the three shapes the correction provably produces: an exact
    18x ratio in either direction, a null against R's literal 0, and Python's
    numeric sentinel against a reading outside the analytical range. R-null
    cells are excluded, because that population predates this change and belongs
    to the still-open baseline-FBG join question.
    """
    if m.column not in GLUCOSE_UNIT_COLUMNS:
        return False
    r = _glucose_float(m.r_value)
    if r is None:
        return False

    py = _glucose_float(m.py_value)
    if py is None:
        return r == 0.0

    if py == settings.error_val_numeric:
        low, high = (
            (MG_ANALYTICAL_MIN, MG_ANALYTICAL_MAX)
            if m.column.endswith("_mg")
            else (MMOL_ANALYTICAL_MIN, MMOL_ANALYTICAL_MAX)
        )
        return r < low or r > high

    for expected in (r * MMOL_TO_MG_FACTOR, r / MMOL_TO_MG_FACTOR):
        if abs(py - expected) <= max(1e-6, abs(expected) * 1e-4):
            return True
    return False


PATIENT_GLUCOSE_UNIT_CLASSIFIERS: dict[str, Classifier] = {
    "python_glucose_unit_corrected": _is_python_glucose_unit_corrected,
}


def _is_wide_format_fragment_truncated(m: CellMismatch) -> bool:
    """R's value is a truncated prefix of Python's for a 2017-2019 Mandalay
    wide-format ``product_units_released`` cell.

    ``handle_wide_format_cells`` (extract/wide_format.py) splits a
    comma-separated "Released To" cell on commas, then each fragment on its
    first ``-`` into (name, qty). Verified against the real source Excel
    (ticket 24, e.g. 2019_Mandalay Children's Hospital Feb19!K49:
    "MM_QA019-2(Error-1),..."): the source cell's free-text notes contain
    embedded parentheses and extra hyphens the split logic doesn't fully
    anticipate. Python's qty fragment keeps the full remainder after the
    first ``-``; R's equivalent step drops content after a second hyphen,
    so R's value is consistently a strict prefix of Python's for the same
    cell -- a genuine R parsing gap on inherently messy source notes, not a
    Python bug, and not something to "fix" toward R's more-truncated answer.
    """
    r_str, py_str = str(m.r_value), str(m.py_value)
    return r_str != py_str and py_str.startswith(r_str)


WIDE_FORMAT_FRAGMENT_CLASSIFIERS: dict[str, Classifier] = {
    "wide_format_fragment_truncated": _is_wide_format_fragment_truncated,
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


@dataclass(frozen=True)
class DirectorySummary:
    """Whole-arm rollup of a DirectoryComparison.

    Each measure is ``(files_affected, total)`` -- the per-file table shows
    where a divergence is, this shows how much of it there is overall, which
    is otherwise only obtainable by scrolling every year's table.
    """

    files_compared: int
    shape_mismatch_files: int
    id_divergence: tuple[int, int]
    column_divergence: tuple[int, int]
    categorical_divergence: tuple[int, int]
    totals_divergence: tuple[int, int]
    row_key_divergence: tuple[int, int]
    cell_divergence: tuple[int, int]
    only_in_r: int
    only_in_py: int


def summarize_directory(comparison: DirectoryComparison) -> DirectorySummary:
    """Roll a DirectoryComparison up into per-measure (files affected, total)."""

    def rollup(per_file: list[int]) -> tuple[int, int]:
        return sum(1 for n in per_file if n), sum(per_file)

    files = comparison.files
    return DirectorySummary(
        files_compared=len(files),
        shape_mismatch_files=sum(1 for f in files if not f.shape.match),
        id_divergence=rollup(
            [
                0
                if f.id_overlap is None
                else len(f.id_overlap.only_in_r) + len(f.id_overlap.only_in_py)
                for f in files
            ]
        ),
        column_divergence=rollup(
            [
                len(f.columns.only_in_r)
                + len(f.columns.only_in_py)
                + len(f.columns.dtype_mismatches)
                for f in files
            ]
        ),
        categorical_divergence=rollup([len(f.categorical_overlap) for f in files]),
        totals_divergence=rollup([len(f.totals) for f in files]),
        row_key_divergence=rollup(
            [f.row_key_overlap.r_unmatched + f.row_key_overlap.py_unmatched for f in files]
        ),
        cell_divergence=rollup([len(f.cell_mismatches) for f in files]),
        only_in_r=len(comparison.only_in_r),
        only_in_py=len(comparison.only_in_py),
    )


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


_R_BLANK_HEADER_COLUMN = re.compile(r"^na\d*(\.(monthly|static|\d+))*$")


def classify_column_divergence(kind: str, column: str, r_only: set[str], py_only: set[str]) -> str:
    """Name why a column exists on one side of the comparison only.

    Two structural causes account for almost all of the patient raw stage's
    divergence, and neither is a content difference:

    - `r_blank_header_artifact`: R's `make.names(header_cols, unique = TRUE)`
      (script1_helper_read_patient_data.R) renders a blank header cell as the
      *string* "NA.", so the following `is.na(colnames(...))` drop never fires
      and every spacer column survives as na, na1, ... na10064. Python drops
      blank-header columns in `filter_valid_columns`, so it has no equivalent.
    - `name_sanitization_only`: both sides carry the column, but R stores the
      sanitized name ("currentinsulinregimen") where Python's raw stage keeps
      the literal source header ("Current Insulin Regimen").

    Checked in that order: R's artifact name would otherwise be masked by any
    Python column that happens to sanitize to "na".
    """
    if kind == "only in R" and _R_BLANK_HEADER_COLUMN.match(column):
        return "r_blank_header_artifact"

    other = py_only if kind == "only in R" else r_only
    if sanitize_str(column) in {sanitize_str(c) for c in other}:
        return "name_sanitization_only"

    return "unclassified"


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

        r_only = set(file_comparison.columns.only_in_r)
        py_only = set(file_comparison.columns.only_in_py)

        for column in file_comparison.columns.only_in_r:
            column_divergence_rows.append(
                {
                    "file": name,
                    "column": column,
                    "kind": "only in R",
                    "r_dtype": "",
                    "py_dtype": "",
                    "cause": classify_column_divergence("only in R", column, r_only, py_only),
                }
            )
        for column in file_comparison.columns.only_in_py:
            column_divergence_rows.append(
                {
                    "file": name,
                    "column": column,
                    "kind": "only in Python",
                    "r_dtype": "",
                    "py_dtype": "",
                    "cause": classify_column_divergence("only in Python", column, r_only, py_only),
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
                    "cause": "unclassified",
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
