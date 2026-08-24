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

from a4d.clean.date_parser import EXCEL_EPOCH, parse_date_flexible
from a4d.clean.glucose import (
    GLUCOSE_COLUMN_PAIRS,
    MG_ANALYTICAL_MAX,
    MG_ANALYTICAL_MIN,
    MMOL_ANALYTICAL_MAX,
    MMOL_ANALYTICAL_MIN,
    MMOL_TO_MG_FACTOR,
)
from a4d.clean.glucose import (
    GLUCOSE_COLUMNS as GLUCOSE_UNIT_COLUMNS,
)
from a4d.clean.validators import load_numeric_ranges, load_validation_rules, sanitize_str
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


def string_numeric_normalize_targets(df: pl.DataFrame, exclude: Sequence[str]) -> list[str]:
    """Cleaned-stage columns to parse back to ``float`` before diffing.

    Cleaning casts its numeric columns, which is why ticket 22 scoped numeric
    normalization to the raw stage. The exception is a column the cleaned
    schema types as a **string** -- a screening measurement that can also read
    "normal", an hba1c that can read "<7" -- which cleaning therefore never
    casts, so R's and Python's differing float-to-string rounding
    (``4.8600000000000003`` against ``4.86``) survives into the cleaned output
    exactly as it does at the raw stage.

    Derived from the frame's own dtypes rather than named, for the same reason
    ``numeric_normalize_targets`` is: which columns are string-typed is the
    schema's decision, and a hand-written copy of it drifts.
    """
    excluded = set(exclude)
    return [
        name
        for name, dtype in df.schema.items()
        if dtype == pl.String and name not in excluded and not name.startswith("__")
    ]


def normalize_boolean_literal_column(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Fold R's and Python's spellings of a boolean cell together.

    Where a source cell holds a genuine Excel boolean, readxl reads a logical
    and R writes it as ``FALSE``; openpyxl reads a Python ``bool`` and Python
    writes it as ``False``. Only an actual Excel boolean produces both
    spellings at once, so this is a language convention, not a divergence --
    confirmed at the cleaned stage, where both sides already agree because
    cleaning canonicalizes them (ticket 49: 20 raw-stage mismatches on
    clinic_visit/remote_followup, 0 cleaned-stage). Only the exact literals
    are folded, so free text that merely contains "false" is untouched.
    """
    if column not in df.columns:
        return df
    lowered = pl.col(column).str.to_lowercase()
    return df.with_columns(
        pl.when(lowered.is_in(["true", "false"]))
        .then(lowered)
        .otherwise(pl.col(column))
        .alias(column)
    )


def whitespace_normalize_targets(df: pl.DataFrame, exclude: Sequence[str]) -> list[str]:
    """Raw-stage columns to strip and line-ending-normalize before diffing.

    Scoped like ``numeric_normalize_targets`` and for the same reason: the
    cleaned patient schema, though derived rather than hand-written, is the
    wrong source at the raw stage. ``get_string_columns()`` omits raw-only
    columns entirely (``dm_complications`` has no cleaned equivalent) and
    types as ``Float64`` columns the raw stage still holds as text
    (``insulin_injections``, ``hba1c_updated``), so readxl's ``trim_ws`` and
    its ``\\r\\n`` line endings kept surfacing on exactly those columns as
    mismatches while every cleaned-schema string column was already handled.
    Since the raw stage stores every value as text, the correct scope is
    every string column.
    """
    excluded = set(exclude)
    return [
        name
        for name, dtype in df.schema.items()
        if name not in excluded and not name.startswith("__") and dtype == pl.String
    ]


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


UnmatchedKey = tuple[tuple[Any, ...], int]


@dataclass(frozen=True)
class RowKeyOverlap:
    """How many rows found a partner via the row-alignment key -- and which
    did not.

    The counts alone proved insufficient in practice (ticket 47): the four
    patient rows this measure newly flagged could only be named by querying
    the parquets by hand, because a row that finds no partner never reaches a
    cell comparison and so appears in no other sheet of the report. The keys
    are therefore carried alongside the counts, each with the number of
    surplus rows on that side, so a divergence can be triaged from the report
    itself.
    """

    matched: int
    r_unmatched: int
    py_unmatched: int
    r_only_keys: tuple[UnmatchedKey, ...] = ()
    py_only_keys: tuple[UnmatchedKey, ...] = ()


def compare_row_key_overlap(
    r_df: pl.DataFrame, py_df: pl.DataFrame, key_cols: list[str]
) -> RowKeyOverlap:
    r_counts = Counter(r_df.select(key_cols).iter_rows())
    py_counts = Counter(py_df.select(key_cols).iter_rows())

    matched = 0
    r_unmatched = 0
    py_unmatched = 0
    r_only: list[UnmatchedKey] = []
    py_only: list[UnmatchedKey] = []
    for key in r_counts.keys() | py_counts.keys():
        r_count, py_count = r_counts.get(key, 0), py_counts.get(key, 0)
        paired = min(r_count, py_count)
        matched += paired
        r_unmatched += r_count - paired
        py_unmatched += py_count - paired
        if r_count > paired:
            r_only.append((key, r_count - paired))
        if py_count > paired:
            py_only.append((key, py_count - paired))

    # Sorted on the rendered key so a report diffs cleanly run over run, and
    # so a key holding nulls or mixed types cannot raise on comparison.
    def rendered(item: UnmatchedKey) -> tuple[str, ...]:
        return tuple(str(part) for part in item[0])

    return RowKeyOverlap(
        matched=matched,
        r_unmatched=r_unmatched,
        py_unmatched=py_unmatched,
        r_only_keys=tuple(sorted(r_only, key=rendered)),
        py_only_keys=tuple(sorted(py_only, key=rendered)),
    )


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
    # Set by compare_cells when order_group_cols is given: True if r_value,
    # read as a Buddhist-era date and shifted to Gregorian, appears in the
    # Python side's own group for this column (ticket 61). The cleaned stage's
    # conversion re-sorts the converted row, and R's unconverted value is by
    # construction absent from Python's group -- so plain value membership
    # cannot see this re-sort, only the shifted value can.
    era_shift_row_order_candidate: bool = False
    # Set by compare_cells when order_group_cols is given and the key is
    # positional: True if this column's value on the group's LAST row agrees
    # on both sides. For a derived running total (product_balance), which is
    # recomputed per row and so cannot travel with its row under a re-sort,
    # this is the order-independent evidence row_order_candidate cannot
    # supply -- the ledgers took different paths to the same closing figure
    # (ticket 36). Diagnostic only, like row_order_candidate.
    group_endpoint_matches: bool = False
    # Set by compare_cells: True if any *other* column on this same row is
    # itself a bare-year mismatch (ticket 52). age and t1d_diagnosis_age are
    # derived from dob and t1d_diagnosis_date, so when one of those carries a
    # bare year the two pipelines derive from different birth years -- a
    # cascade of an already-decided cause, not a separate divergence. Keyed on
    # the mechanism rather than on the derived values' shape, which alone
    # cannot tell this apart from a genuine age disagreement.
    row_has_bare_year_date: bool = False
    # Set by compare_cells when unit_swapped_columns is given (ticket 44):
    # True if this cell's glucose column pair was unit-swapped in this file.
    # Whether a column is really recorded in mmol/L is a property of the whole
    # column, so no per-cell test can establish it -- ticket 57 left six cells
    # unclassified for exactly this reason. The fact is read back from the
    # pipeline's own glucose_unit_swapped error records, not re-derived here.
    column_unit_swapped: bool = False
    # Set by compare_cells (ticket 44): for a mmol glucose column, the
    # (r_value, py_value) of the same row's mg sibling. The mmol column is not
    # independently recorded -- both pipelines derive it from the mg cell -- so
    # the sibling is what says whether an mmol divergence is its own or an
    # already-named one restated.
    mg_sibling: tuple[Any, Any] | None = None
    # Set by compare_cells when tracker_year_col is given (ticket 32): the
    # tracker's own calendar year, taken from the Python side's own column
    # rather than parsed out of the file name. It is what lets a classifier ask
    # whether Python's *own* value is plausible for this tracker, instead of
    # only describing how the two sides differ.
    tracker_year: int | None = None


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
    unit_swapped_columns: set[str] | None = None,
    tracker_year_col: str | None = None,
) -> list[CellMismatch]:
    """Diff matched rows cell-by-cell.

    ``unit_swapped_columns`` (ticket 44) is this file's set of mg/dL-labelled
    glucose columns that ``resolve_glucose_units`` found to be recorded in
    mmol/L, taken from the run's own error records. Both halves of an affected
    pair are flagged, since the correction moves values between them.

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
    swapped_pair_columns = _swapped_pair_columns(unit_swapped_columns)
    mg_by_mmol = {
        mmol: mg for mg, mmol in GLUCOSE_COLUMN_PAIRS if mmol in value_cols and mg in value_cols
    }

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

    # A value column is suffixed on the Python side by the join; a key column
    # is shared, so it is not.
    year_field = None
    if tracker_year_col:
        for candidate in (f"{tracker_year_col}_py", tracker_year_col):
            if candidate in joined.columns:
                year_field = candidate
                break

    mismatches = []
    for row in joined.iter_rows(named=True):
        key = {k: row[k] for k in key_cols}
        tracker_year = _as_year(row[year_field]) if year_field else None
        gkey = tuple(row[c] for c in order_group_cols) if order_group_cols else None
        has_bare_year = any(
            _is_python_reads_bare_year(
                CellMismatch(key=key, column=c, r_value=row[c], py_value=row[f"{c}_py"])
            )
            for c in value_cols
        )
        for col in value_cols:
            r_value, py_value = row[col], row[f"{col}_py"]
            if _values_differ(r_value, py_value):
                row_order_candidate = False
                era_shift_row_order_candidate = False
                if gkey is not None:
                    counts = group_value_counts.get(gkey, {}).get(col)
                    row_order_candidate = bool(counts) and counts[r_value] > 0
                    shifted = _shift_from_buddhist_era(r_value)
                    era_shift_row_order_candidate = (
                        bool(counts) and shifted is not None and counts[shifted] > 0
                    )
                mismatches.append(
                    CellMismatch(
                        key=key,
                        column=col,
                        r_value=r_value,
                        py_value=py_value,
                        row_order_candidate=row_order_candidate,
                        era_shift_row_order_candidate=era_shift_row_order_candidate,
                        group_endpoint_matches=group_endpoint_agrees.get((gkey, col), False),
                        row_has_bare_year_date=has_bare_year,
                        column_unit_swapped=col in swapped_pair_columns,
                        mg_sibling=(
                            (row[mg_col], row[f"{mg_col}_py"])
                            if (mg_col := mg_by_mmol.get(col)) is not None
                            else None
                        ),
                        tracker_year=tracker_year,
                    )
                )
    return mismatches


def _as_year(value: Any) -> int | None:
    """The tracker year column is Float64 on one side and Int32 on the other."""
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _swapped_pair_columns(unit_swapped_columns: set[str] | None) -> set[str]:
    """Both halves of every swapped glucose pair.

    ``resolve_glucose_units`` records the swap against the mg/dL column it read
    as mmol/L, but the correction empties that column into its mmol sibling, so
    a cell on either side of the pair is affected by the same file-level fact.
    """
    if not unit_swapped_columns:
        return set()
    swapped = set(unit_swapped_columns)
    for mg_col, mmol_col in GLUCOSE_COLUMN_PAIRS:
        if mg_col in unit_swapped_columns:
            swapped.add(mmol_col)
    return swapped


GLUCOSE_UNIT_SWAP_ERROR_CODE = "glucose_unit_swapped"


def load_glucose_unit_swaps(errors: pl.DataFrame) -> dict[str, set[str]]:
    """Per tracker, which glucose columns the pipeline read as mmol/L.

    Derived from the run's own error table rather than restated in the
    comparison: ``resolve_glucose_units`` already writes one
    ``glucose_unit_swapped`` row per affected file-column, so a threshold
    change in the pipeline reaches the comparison without a second edit.
    """
    swapped = errors.filter(pl.col("error_code") == GLUCOSE_UNIT_SWAP_ERROR_CODE)
    by_tracker: dict[str, set[str]] = {}
    for row in swapped.iter_rows(named=True):
        by_tracker.setdefault(row["file_name"], set()).add(row["column"])
    return by_tracker


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

# Mirrors the product pipeline's own BUDDHIST_ERA_OFFSET / YEAR_FLOOR_DELTA, so
# a date the pipeline treats as this tracker's Buddhist-era year is not then
# called absurd here.
BUDDHIST_ERA_OFFSET = 543
YEAR_FLOOR_DELTA = 5

# Excel's 1900 date system counts a 29 February 1900 that never existed, so
# serials below 61 resolve one day apart depending on whether the reader
# reproduces the bug (openpyxl) or does plain epoch arithmetic.
EXCEL_LEAP_BUG_YEAR = 1900
EXCEL_LEAP_BUG_CUTOFF = datetime.date(1900, 3, 1)


def _is_python_sentinel_r_extraction_gap(m: CellMismatch) -> bool:
    """Python declined the cell and R never read it.

    Verified against source (ticket 32): 25 of the 78 current rows are
    Sarawak's 2023 tracker, whose ``Dec23`` sheet genuinely carries December
    *2024* entry dates. Python's beyond-tracker-year guard
    (``_validate_entry_dates``) stamps the sentinel; R's cleaned side is null
    for the same reason ``r_value_missing`` describes. Both halves are
    already-decided mechanisms -- this names their intersection, which the
    earlier ``sentinel_null`` described only by its shape.
    """
    return m.r_value is None and m.py_value == SENTINEL_DATE


def _is_python_out_of_window_date_preserved(m: CellMismatch) -> bool:
    """Python published a date from outside the tracker's own window.

    ``_validate_entry_dates``'s year-floor branch logs these and deliberately
    keeps the parsed date, so the downstream sort matches R's. That is a
    decision the pipeline already made and reports; what it must not do is
    ride along inside ``r_value_missing``, which asserts the opposite -- that
    Python read the cell correctly and R lost it. Ticket 32 found 19 such rows
    there, including ``0202-06-20`` (Surat Thani) and seven ``2009-12-04`` in a
    2019 Mahosot tracker. Each is a corrupt source cell, so the workbook is the
    fix (ticket 40), not the classifier.
    """
    return (
        m.r_value is None
        and isinstance(m.py_value, datetime.date)
        and m.py_value != SENTINEL_DATE
        and m.tracker_year is not None
        and not (m.tracker_year - YEAR_FLOOR_DELTA <= m.py_value.year <= m.tracker_year)
    )


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

    Bounded by ``_is_python_out_of_window_date_preserved`` and
    ``_is_python_absurd_excel_serial``, which run first: this cause asserts
    Python read the cell correctly, so it may not cover a cell whose Python
    value is itself implausible (ticket 32).
    """
    return m.r_value is None and m.py_value is not None and m.py_value != SENTINEL_DATE


def _is_python_absurd_excel_serial(m: CellMismatch) -> bool:
    """Python turned a corrupt Excel serial into a date centuries away.

    Replaces ``ce_typo``, which tested ``r_value.year > 2100`` and so fired on
    ``normalize_date_column``'s own 9999 sentinel while saying nothing about
    the Python side. Both current rows are junk source serials -- 1,339,576
    published as ``5567-08-19`` (2024 Chiang Mai) and 411,384 as
    ``3026-04-30`` (2026 Penang). The cleaned stage no longer publishes these
    (``implausible_era_date``, ticket 32), so the cause remains for the raw
    stage, where extraction has no validation.

    A genuine Buddhist-era date is *not* this: BE serials (~243,933) land on
    the tracker's own BE year and are excluded by the band check.
    """
    if not isinstance(m.py_value, datetime.date) or m.py_value == SENTINEL_DATE:
        return False
    if m.py_value.year < CE_TYPO_YEAR_THRESHOLD:
        return False
    # Patient stages carry no tracker_year column, so the band would never
    # apply there and the cause would out-claim genuine Buddhist-era dates
    # (ticket 60). _sheet_year reads the same year off the row's sheet name.
    tracker_year = m.tracker_year if m.tracker_year is not None else _sheet_year(m)
    if tracker_year is not None:
        buddhist_year = tracker_year + BUDDHIST_ERA_OFFSET
        if buddhist_year - YEAR_FLOOR_DELTA <= m.py_value.year <= buddhist_year:
            return False
    return True


# Wired ahead of every patient date column's own causes (ticket 60). Safe to
# run first because the band check above excludes a genuine Buddhist-era year,
# and a junk serial is not evidence about R's parse orders -- it was
# `r_parse_order_cannot_read_cell` that claimed the five 2025 Surat Thani cells
# whose R side is the serial 1141523.
PATIENT_ABSURD_SERIAL_CLASSIFIERS: dict[str, Classifier] = {
    "python_absurd_excel_serial": _is_python_absurd_excel_serial,
}


def _is_excel_1900_leap_serial(m: CellMismatch) -> bool:
    """One day apart because Excel believes 1900 was a leap year.

    A serial below 61 predates the phantom 1900-02-29: openpyxl reproduces
    Excel's own reading (serial 25 -> 1900-01-25) while plain epoch arithmetic
    from 1899-12-30, which ``normalize_date_column`` does via
    ``parse_date_flexible``, gives 1900-01-24. Both sides are reading the same
    source integer (ticket 32), which is stray end-of-block summary residue in
    both current rows -- the cleaned stage nulls it (``summary_residue_nulled``).
    """
    return (
        isinstance(m.r_value, datetime.date)
        and isinstance(m.py_value, datetime.date)
        and m.r_value.year == EXCEL_LEAP_BUG_YEAR
        and m.py_value.year == EXCEL_LEAP_BUG_YEAR
        and m.py_value < EXCEL_LEAP_BUG_CUTOFF
        and (m.py_value - m.r_value).days == 1
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


# Order matters: the two bounds on r_value_missing must run before it, or it
# absorbs the cells they exist to expose (ticket 32).
PRODUCT_ENTRY_DATE_CLASSIFIERS: dict[str, Classifier] = {
    "python_sentinel_r_extraction_gap": _is_python_sentinel_r_extraction_gap,
    "excel_1900_leap_serial": _is_excel_1900_leap_serial,
    "python_absurd_excel_serial": _is_python_absurd_excel_serial,
    "python_out_of_window_date_preserved": _is_python_out_of_window_date_preserved,
    "r_value_missing": _is_r_value_missing,
    "python_future_date_sentinel": _is_python_future_date_sentinel,
    "summary_residue_nulled": _is_summary_residue_nulled,
}

# The patient arm's cleaned stage runs the same future-date guard, so its date
# columns need the same cause without the product-specific siblings above.
PATIENT_FUTURE_DATE_CLASSIFIERS: dict[str, Classifier] = {
    "python_future_date_sentinel": _is_python_future_date_sentinel,
}


def _is_r_category_lookup_miss(m: CellMismatch) -> bool:
    """R's category join missed a product Python resolved.

    ``add_product_categories`` (read_product_data.R:481) is a bare
    ``dplyr::left_join`` on the raw ``product`` string;
    ``load_product_reference_data`` lowercases only the *column names* of the
    Stock_Summary sheet, never the values. Python's ``_add_product_categories``
    (clean/product.py) lowercases both sides before joining.

    Ticket 62 scanned the whole population (866 rows, 12 files, 29 distinct
    product names) and found **two** mechanisms, not the one this docstring
    used to name. Python is the correct side in both; R loses a category the
    reference data can supply.

    - **CRLF vs LF, 652 rows over 26 names.** Not a property of R's join at
      all -- the two sides never see the same string. The reference workbook
      stores embedded line breaks as a bare ``\\n`` (executed: its
      Stock_Summary sheet XML holds 29 LF bytes and **zero** CR bytes), while
      the trackers store ``\\r\\n`` (2021 Surat Thani's sharedStrings holds 80
      CRLF pairs). readxl returns each faithfully, so R compares
      ``'Accu-Chek Performa Test Strips \\r\\n(50s/ bottle)'`` against a
      reference entry spelled with ``\\n`` and misses; openpyxl normalises
      CRLF to LF on read, so Python's strings match byte-for-byte. This is
      the same reader difference ``normalize_whitespace_column`` was added
      for in ticket 22, surfacing here as a lookup failure.
    - **Case, 214 rows over 3 names.** The documented mechanism, and the only
      one it covers: ``'NovoFine Needles 4mm x 32G (singles)'`` against the
      reference's ``'(Singles)'`` (98), ``'ACCU-CHEK Performa Glucometer Set'``
      against ``'Accu-Chek Performa Glucometer Set'`` (91), and the same
      ``(singles)`` slip on NIPRO (25).

    Caveat worth carrying: Python matches the 26 CRLF names by luck, not by
    design -- its join normalises case only, and it works solely because
    openpyxl happens to fold the line endings. A reference entry typed with
    CRLF against a tracker spelled with LF would miss on Python too. Nothing
    in the current data triggers that, so it is recorded rather than fixed.
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

    **Verdict (ticket 60): Python's chronological sort is the correct side.**
    The mechanism was established by ticket 21 and the evidence by ticket 25 --
    per-column multiset equality across all 2,283 ``(clinic_id,
    product_sheet_name)`` groups for ``product_units_released``, and row-identity
    preservation across all 11,649 product groups -- but the verdict itself was
    never written down, only implied. Stating it plainly: both sides implement
    the same documented rank algorithm, the difference is entirely in which
    rows have a parsable ``product_entry_date`` to sort by, and Python parses
    the ones R does not. Nothing is added or lost on either side; only the
    order differs.

    Caveat on the flag, not on the verdict: ``row_order_candidate`` is a loose
    value-membership test -- it asks whether R's value appears anywhere in
    Python's own group -- so it false-fires on repeated small numeric values,
    where a coincidental match means nothing. It is evidence of ordering, not
    proof of it, and ``product_balance``'s cumulative running total cannot be
    detected this way at all (already explained, and homed on ticket 36).
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

    Ticket 50 adds three more, each verified against the source workbook and
    against R's own raw parquet, which carries the column R could not name:

    - ``hospitalisation_date``/``hospitalisation_cause`` on 2022 Kantha Bopha:
      the upper header cell (X71) opens with thirteen spaces, so R's merged
      header starts with a space and its name sanitizer emits
      ``xcurrentmonthhospitalisationdkahypootherdropdown``/``...date``, which no
      synonym matches -- the same leading-space mechanism as ``edu_occ_updated``
      above. The source plainly records "DKA" and a date (Sept'22!X92/Y92 for
      KH_QD020, Nov'22 and Dec'22 for KH_QD113).
    - ``fbg_updated_date`` on 2019 Preah Kossamak: the Jul19 and Aug19 sheets
      lost the header merges every other month sheet still has (only B63:B64
      survives), so the "Updated FBG" title no longer spans its "Date"
      sub-header. R pastes the two header rows per column and is left with a
      bare ``date`` column it cannot map; Python forward-fills the upper header
      row and recovers the qualified name. Verified: Jul19!O66 = 2019-06-06 for
      KH_QF002, exactly Python's value, and R has 0 non-null for both sheets
      against Python's 13 and 12.
    - ``clinic_visit`` on 2025 LWCH: the column holding the current-month visit
      flag (D) has no header in *either* header row, so R drops it; Python
      recovers the name from the sibling month sheets that do label it (ticket
      30's ``recover_blank_headers``). Verified: Oct25!D90 = "Y" for MY_QC014.

    Ticket 60 scanned the whole population rather than the columns already
    named, and found it spans thirteen columns, not the seven above. Three
    further mechanisms, each traced to the source workbook, each with Python
    the correct side:

    - ``insulin_regimen`` on 2021 Kantha Bopha (194 rows): the ``Mar21`` and
      ``Apr21`` sheets carry the patient header at row 85 with ``Q85``/``Q86``
      simply *empty*, where every other month sheet has ``Q13 = "Insulin
      Regime"``. R publishes 0 non-null for those two sheets and 97 for each of
      the others; the column still holds data (``Mar21!Q87 = "Self-mixed BD"``
      for KH_QD001), and Python recovers the name from the sibling sheets via
      ``recover_blank_headers``. The same blank-header mechanism as
      ``clinic_visit`` above, a second instance rather than a new kind.
    - **A blank row number on the 2026 ``Annual`` sheet** (7 rows): 2026 ISDFI
      rows 32-34 (PH_QC022-024) and 2026 Khon Kaen row 27 (TH_QD016) are
      exactly the ``Annual`` rows whose column A is empty while every other row
      is numbered. R drops them from the Annual join and publishes null across
      ``edu_occ``, ``blood_pressure_sys_mmhg``, ``blood_pressure_dias_mmhg``,
      ``other_issues`` and ``status``; the cells hold real values
      (``Annual!E32 = "college graduate"``, ``H32``/``I32`` = 80/50). Note this
      corrects the reason recorded against those same ISDFI cells further up
      the registry, which attributes them to R reading nothing from the Annual
      sheet: R reads that sheet for this file perfectly well (102 of 120
      ``edu_occ``), so the sheet is not the mechanism, the missing row number
      is.
    - ``edu_occ`` on 2026 Nakornping (42 rows, R 0 non-null for the whole
      file): its ``Annual!E9`` reads ``"Level of Education\\nOr Occupation/
      อาชีพหรือชั้นเรียน"`` where ISDFI's and Khon Kaen's read ``"Level of
      Education\\nOr Occupation"``. R's Unicode-aware sanitizer keeps the Thai
      in the column name and no synonym matches; Python's ASCII folding drops
      it. This is ``r_non_latin_header_miss``'s mechanism (ticket 49) being
      absorbed here on registry order -- worth knowing, not a defect.

    Ticket 62 measured the two populations ticket 60 left, which are 98% of
    the cause. Python is correct in both; the mechanism is sharper than the
    entry above states.

    - ``recruitment_date`` (28,009 rows, 94 files). The claim above -- R's
      extraction "fails to populate it for the large majority of patients" --
      is **false**: R populates 53,331 of its 82,771 raw rows (64%). The
      divergence is perfectly file-level and all-or-nothing. Measured over the
      239 comparable files: 91 where R reads **zero** recruitment dates and
      Python reads them, 148 with no divergence at all, and **zero** files
      where R reads some and misses others. The cause is a header cell whose
      text ends in a space, which forces Excel to write
      ``<t xml:space="preserve">`` (executed: 2023 CDA ``Patient List!L8`` is
      literally ``<c r="L8" ... t="inlineStr"><is><t xml:space="preserve">Date
      of Recruitment </t></is></c>``). R reads its headers with
      ``openxlsx::read.xlsx`` (script1_helper_read_patient_data.R:15), whose
      inline-string parsing folds that attribute into the header text, so
      ``make.names`` emits the column ``xmlspacepreservedateofrecruitmentmmmyy``
      and no synonym matches it. The correlation is exact: all 91 affected
      files carry that column in R's own raw parquet, and none of the other
      148 do. openpyxl parses the attribute correctly and reads
      ``'Date of Recruitment '``. The same defect eats at least one other
      column R never maps
      (``xmlspacepreserveinsurancestatusnanssfeqeqpending``).
    - ``edu_occ_updated`` (2,770 rows, 16 files). Also whole-file rather than
      per-patient (13 files where R reads zero), but unlike recruitment_date
      it is not one mechanism: R's raw output carries three distinct junk
      names for this column across the corpus --
      ``xlevelofeducationoroccupationdate`` (the leading-space fixup
      documented above), ``levelofeducationoroccupationอาชพหรอชนเรยน`` and
      ``...dateupdatedddmmmyyyy`` (ticket 60's Thai-header mechanism). Fifteen
      files carry a junk name *and* still resolve the column, so the junk name
      alone is not sufficient to predict the loss here the way it is for
      recruitment_date.

    A genuine R limitation in every case, not a Python defect.
    """
    return m.r_value is None and m.py_value is not None


PATIENT_R_EXTRACTION_GAP_CLASSIFIERS: dict[str, Classifier] = {
    "r_extraction_gap": _is_r_extraction_gap,
}


def _is_r_duplicate_header_selection_dropped(m: CellMismatch) -> bool:
    """R keeps only the first selection of a multi-select block; Python keeps all.

    Where a merged screening header spans several "(Select)" sub-columns that
    all map to one canonical name, R's ``make.names(unique = TRUE)`` suffixes
    the duplicates and its mapping then keeps only the first -- verified in R's
    own raw parquet for 2021 NPH, which carries the second selection in
    ``complicationscreeningselect1`` rather than in ``complication_screening``.
    Python unites the whole group (ticket 31), so it carries both. The source
    records both (Dec21!AD84 "Dilated Eye Examination", AE84 "Foot Examination
    (Nerves)" for KH_QE006), so Python is the correct side and R is losing a
    recorded screening.

    Fires only where R's value is exactly Python's own first selection, so a
    group whose *kept* selection disagrees stays unclassified.
    """
    if m.r_value is None or m.py_value is None:
        return False
    py_parts = str(m.py_value).split(",")
    return len(py_parts) > 1 and py_parts[0].strip() == str(m.r_value).strip()


PATIENT_SCREENING_SELECTION_CLASSIFIERS: dict[str, Classifier] = {
    "r_duplicate_header_selection_dropped": _is_r_duplicate_header_selection_dropped,
}


def _is_r_non_latin_header_miss(m: CellMismatch) -> bool:
    """R's header sanitizer keeps non-Latin script, so its exact match fails.

    ``harmonize_patient_data_columns`` (script1_helper_read_patient_data.R)
    resolves a header by ``match()`` -- exact equality against the sanitized
    synonym list -- after ``sanitize_str`` strips ``[^[:alnum:]]``. R's
    character class is Unicode-aware, so a clinic that appends a local-language
    translation to the English header keeps it: "Last Clinic \\nVisit\\n
    <Thai>" sanitizes to ``lastclinicvisit<Thai>``, which equals no synonym, so
    R drops the column and leaves every row null. Python's ``sanitize_str``
    (src/a4d/reference/synonyms.py) strips to ``[^a-z0-9]`` instead, reducing
    the same header to ``lastclinicvisit`` and matching.

    Executed both implementations on the real header to confirm the divergence
    rather than reading the two regexes. Verified against the real source Excel
    (2022 Mukdahan, Mar22!F44/G44 carry Thai suffixes; F46 = 2022-02-17, which
    is Python's 44609): Python recovers 44 real dates R discards. A genuine R
    limitation, not a Python defect -- and the reason Python's own docstring
    claim that its sanitizer "matches the R implementation" is not exactly
    true here.
    """
    return m.r_value is None and m.py_value is not None


PATIENT_NON_LATIN_HEADER_CLASSIFIERS: dict[str, Classifier] = {
    "r_non_latin_header_miss": _is_r_non_latin_header_miss,
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


def _shift_from_buddhist_era(value: Any) -> datetime.date | None:
    """``value`` read as a Buddhist-era date and shifted to Gregorian, or None.

    None whenever the shift is not meaningful: the value is not a date, its
    year is plausible as Gregorian already, or the shifted day does not exist
    (a Buddhist leap day, which the pipeline declines to convert for the same
    reason).
    """
    as_date = _as_date(value)
    if as_date is None or as_date.year < PATIENT_BUDDHIST_ERA_THRESHOLD:
        return None
    try:
        return as_date.replace(year=as_date.year - BUDDHIST_ERA_OFFSET)
    except ValueError:
        return None


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

    Ticket 60 measured the population and found the name covers **two** R
    defects, not one. 570 of the 15,647 rows have a Python value with no comma
    in it at all -- 510 of them a bare ``Pre-mixed`` -- which the multi-value
    story cannot explain, since R accepts ``Pre-mixed`` elsewhere (5,426 rows
    of its own output). The second mechanism is **NA propagation through R's
    builder**: ``script2_process_patient_data.R`` composes the field as
    ``ifelse(human_insulin_pre_mixed == "Y", "pre-mixed", "")`` pasted with one
    ``ifelse`` per sibling column, and ``NA == "Y"`` is ``NA``, which ``paste``
    stringifies as the literal ``"NA"``. The subsequent ``.x[.x != ""]`` filter
    removes empties but not ``"NA"``, so a single tick beside unfilled siblings
    still yields ``"pre-mixed,NA,NA,NA,NA"`` and is rejected. Measured across
    the corpus: where R publishes ``Pre-mixed``, the sibling columns are
    non-null in 4,134 of 4,135 rows; where R publishes ``Undefined`` on a
    pre-mixed tick, 575 have at least one null sibling. R's output contains no
    comma-joined value at all, and no ``Rapid-acting`` whatsoever -- the latter
    being the ``"rapic-acting"`` typo on line 105 of the same builder.

    Python is the correct side in both: it reads the same raw ticks (verified
    identical on both sides for 2024 NPT, MM_QC009, Apr24) and validates each
    token independently.
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


def _is_r_unicode_sanitizer_rejects_accent(m: CellMismatch) -> bool:
    """A misaccented spelling misses R's allowed-value list but not Python's.

    The two sanitizers were meant to be the same function and are not. R's
    (r-archive/R/script2_sanitize_str.R) strips ``[^[:alnum:]]``, which under
    ICU is Unicode-aware, so accented letters survive; Python's
    (clean/validators.py) strips ``[^a-z0-9]`` and folds them away. Both sides
    sanitize the value and the allowed list before matching, so the difference
    only shows where a source spelling differs from its canonical form in the
    accents alone.

    The whole of this cause on the real 254-tracker set is one Vietnamese
    province across five VNCH trackers: the source writes ``Thái Nguyễn`` (a
    tilde on the second e) where the allowed list has ``Thái Nguyên``. R
    sanitizes those to ``tháinguyễn`` and ``tháinguyên``, misses, and stamps
    the "Undefined" character sentinel; Python sanitizes both to ``thinguyn``
    and recovers the canonical name. Python is right -- the province is real
    and the accent is a typo -- and this is the value-side twin of ticket 49's
    ``r_non_latin_header_miss``, where the same ASCII folding was what let
    Python match a header R could not.

    The folding cannot silently merge two *different* provinces:
    ``validate_allowed_values`` raises on any two allowed values that sanitize
    alike, and the 209-entry province list has no such pair (executed). Note
    what this does *not* fix: the same trackers also write ``Thai Nguyen``
    with no accents at all, which sanitizes to ``thainguyen`` on both sides
    and so is "Undefined" in both pipelines -- a shared limitation the
    comparison cannot see, not a divergence.

    The test is the mechanism: R sentinelled, and Python's canonical value
    carries characters that only Python's sanitizer removes.
    """
    if m.r_value != "Undefined" or not isinstance(m.py_value, str):
        return False
    unicode_aware = m.py_value.lower().replace(" ", "")
    return sanitize_str(m.py_value) != unicode_aware


PATIENT_UNICODE_SANITIZER_CLASSIFIERS: dict[str, Classifier] = {
    "r_unicode_sanitizer_rejects_accent": _is_r_unicode_sanitizer_rejects_accent,
}


PATIENT_INSULIN_SUBTYPE_CLASSIFIERS: dict[str, Classifier] = {
    "r_validator_rejects_multivalue": _is_r_validator_rejects_multivalue,
}


def _is_r_drops_drug_name_tick(m: CellMismatch) -> bool:
    """The clinic ticks an insulin column by naming the drug, and only Python
    reads it.

    The 2024+ template's five insulin columns are tick boxes taking ``Y`` or
    ``-``. 2024 Sarawak General writes the drug instead -- ``Novorapid`` in
    ``analog_insulin_rapid_acting`` and ``Glargine``, ``Toujeo`` or
    ``Ryzodeg`` in ``analog_insulin_long_acting``, across 56 rows. Both
    pipelines tested for ``Y`` exactly, so both discarded the subtype and
    Python's empty derivation was then published as ``Undefined``.

    ``_insulin_ticked`` (clean/patient.py) now reads any value that is not a
    negative marker as a tick, which recovers ``Rapid-acting,Long-acting`` for
    those rows. The negative markers are the closed set the data actually
    holds: across all 248 trackers these columns contain only ``Y``, ``-``,
    ``0``, the four drug names, and null (verified by a distinct-value count
    over the raw output). Python is the correct side -- the clinic did record
    which insulins the patient takes -- and the workbook is a ticket 40
    finding, since free text in a tick box is what made both pipelines lose it.

    Keyed on R holding nothing while Python holds a real subtype list, which
    is the only shape this recovery produces.
    """
    return (
        m.r_value is None
        and isinstance(m.py_value, str)
        and m.py_value not in ("", settings.error_val_character)
    )


PATIENT_INSULIN_DRUG_NAME_CLASSIFIERS: dict[str, Classifier] = {
    "r_drops_drug_name_tick": _is_r_drops_drug_name_tick,
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
    """A non-date column holds a cell carrying an Excel date/time number format.

    The two readers disagree about that cell and nothing else. R's readxl
    infers a whole column's type from its majority values and hands back the
    raw Excel serial; Python's openpyxl reads each cell individually and
    honours its own number format, returning a ``datetime``/``time``. Every
    cell behind this cause was opened in the source workbook and genuinely
    carries such a format, so the *detection* is sound across the whole
    population.

    Ticket 62 measured that population (100 rows, raw stage only, five
    columns across both arms) and found the single verdict this docstring
    used to state -- "Python's value is the faithful one, R's is a coercion
    artifact" -- is right for only a third of it. Three shapes, each with its
    own answer. Note "stray" in the cause name over-reads for two of them;
    the name is kept because ``openpyxl``/``date_typed`` hold for all 100 and
    renaming would orphan the ticket history.

    - **A real date typed into a quantity column** (14 rows): the serial sits
      in the range a 2000-2050 date occupies (43,566-45,652). Verified at
      Penang General 2019 ``Apr19!E36`` ("Units Received", ``d/m/yy``) by
      ticket 24. Python is the correct side, and visibly so downstream --
      ``_is_stray_date_zeroed`` covers the cleaned face, where R carries
      43,708 into the stock ledger and Python zeroes it.
    - **A quantity, or a zero, in a date-formatted cell** (66 rows: 48 with
      an underlying 0 read back as ``00:00:00``, 18 with a genuine count of
      5-200 read back as a 1900 date). Here R's serial *is* the number the
      clinician typed and Python's date is the misleading rendering -- the
      old verdict was backwards. It costs nothing because the divergence does
      not survive cleaning: verified against the real 254-tracker pair that
      both sides publish identical cleaned values for the affected
      (product, sheet) groups, e.g. 2023 Yangon General ``Apr23`` column G,
      whose ``d-mmm-yy`` format sits on cells holding 150, 200, 30, 5 and 0.
      A raw-stage representation artifact, not a data difference, so the
      pipeline is deliberately not changed for it (ticket 32's precedent for
      ``parse_date_flexible``'s epoch: do not move production output to fix a
      raw-stage comparison row).
    - **The patient arm** (20 rows, 5 source cells, 5 trackers), which this
      docstring never mentioned even though ticket 50 wired it -- see the
      ``blood_pressure_mmhg``/``testing_frequency`` note in
      ``scripts/compare_outputs.py``. Each is a value Excel silently
      auto-converted on entry: ``10/60`` becoming Oct-1960 in a
      "Blood Pressure (mm HG)" column (2020 Mahosot ``Nov20!R152``/
      ``Dec20!R153``, 2022 Mahosot ``Jun22!Z323``), ``1-2`` becoming 1-Feb in
      "Testing Frequency (per day)" (2021 Khon Kaen ``Mar21!P60``, whose own
      column holds ``' 1 - 2'`` four rows above), and a diagnosis *date* in
      "Age at Diagnosis" (2023 Chiang Mai ``Patient List!H14``, 2023 Yangon
      General ``Patient List!H76``). Python is unambiguously correct: it
      nulls them, while R publishes diagnosis ages of **20,668** and
      **42,859** years. All five are source defects and already reach the
      errors table as ``type_conversion`` with the original value intact, so
      ticket 40 needs nothing added for them.
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


def _is_stray_date_dropped(m: CellMismatch) -> bool:
    """The same cause again where the cleaned column is integer-typed.

    Ticket 57, one cell: 2021 Khon Kaen Mar21 records a date in
    ``testing_frequency``. R carries the Excel serial (44228) into a column
    meaning "tests per day"; Python's cast fails and leaves null rather than the
    0 its float columns get, so neither of the other two stray-date tests can
    see it. Python is the correct side and the source cell is a defect for
    ticket 40.
    """
    try:
        r_serial = float(m.r_value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return False
    low, high = _PLAUSIBLE_DATE_SERIAL_RANGE
    return low <= r_serial <= high and m.py_value is None


STRAY_DATE_DROPPED_CLASSIFIERS: dict[str, Classifier] = {
    "stray_date_dropped": _is_stray_date_dropped,
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
    """One side carries an Excel formula error string; the other has null.

    **Verdict (ticket 60): Python is the correct side, and the test's symmetry
    is currently unexercised.** Measured over the real 254-tracker pair: all
    12,680 rows run one way -- Python holds the error string, R holds null --
    across ``t1d_diagnosis_age`` (8,495), ``bmi`` (4,170) and ``age`` (15), and
    every one is at the **raw** stage. readxl coerces an Excel error cell to
    NA; openpyxl returns the literal ``#DIV/0!``, which is what raw extraction
    is for -- a faithful record of what the cell contains, including that it
    contains a broken formula rather than a missing value.

    Nothing survives into cleaned output on either side (executed: 0
    error-string cells in all three columns across every cleaned parquet, both
    pipelines), so the divergence is confined to the stage whose job is
    fidelity, and Python's extra information costs the downstream tables
    nothing. The reverse direction is kept in the test because a future tracker
    could produce it, not because anything currently does.
    """
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
    """One side sentinelled a Buddhist-era year the other carried through.

    Bounded by the sheet's own BE band (ticket 60). The bare
    ``year >= PATIENT_BUDDHIST_ERA_THRESHOLD`` test this used to carry claimed
    *any* far-future date as a Buddhist-era typo, which after ticket 61 is
    exactly backwards: the cleaned stage now converts genuine BE dates, so a
    year still sitting above the threshold is by construction not a
    recoverable BE date. Both real populations it was claiming are ordinary
    year typos in the source workbook, verified against the cells themselves
    -- ``3035-03-01`` (2025 CDA, Mar25!O219) and ``5025-05-19`` (2025 Surat
    Thani, May25!O70), each a genuine date-formatted Excel cell whose year is
    neither Gregorian-plausible nor 543 off its tracker's.

    The band mirrors ``_is_python_absurd_excel_serial``'s. Where the sheet
    year cannot be read the old behaviour stands, since an unknown tracker
    year cannot disprove a BE date.
    """
    sentinelled, carried = (
        (m.r_value, m.py_value) if m.r_value == SENTINEL_DATE else (m.py_value, m.r_value)
    )
    if sentinelled != SENTINEL_DATE or not isinstance(carried, datetime.date):
        return False
    if carried.year < PATIENT_BUDDHIST_ERA_THRESHOLD:
        return False
    tracker_year = m.tracker_year if m.tracker_year is not None else _sheet_year(m)
    if tracker_year is None:
        return True
    buddhist_year = tracker_year + BUDDHIST_ERA_OFFSET
    return buddhist_year - YEAR_FLOOR_DELTA <= carried.year <= buddhist_year


def _is_python_buddhist_era_converted(m: CellMismatch) -> bool:
    """R keeps the Buddhist-era year the clinic wrote; Python converts it.

    Ticket 61: a Thai clinic's tracker is kept in a Thai-locale Excel, so its
    dates arrive with a Buddhist-era year (BE = CE + 543) -- the calendar the
    clinic uses, not an error it made. The cleaned stage now shifts those to
    Gregorian (``_convert_buddhist_era_dates``, clean/patient.py, and the BE
    band in ``_validate_entry_dates``, clean/product.py), so downstream reads
    one calendar. R does not convert, which makes this a deliberate divergence
    rather than a defect on either side.

    On the patient arm it is also a recovery: before the conversion existed,
    ``_validate_dates`` saw a year centuries ahead and clobbered the cell with
    the sentinel, so 375 readings were destroyed rather than merely published
    oddly.

    The test is the shift itself -- R's year is implausible as Gregorian, and
    Python's date is exactly the same day 543 years earlier. Anything else
    riding along (a day that also moves, a row-order shift) fails it, so a
    second divergence cannot hide behind this name.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    if r_date is None or py_date is None or SENTINEL_DATE in (r_date, py_date):
        return False
    return (
        r_date.year >= PATIENT_BUDDHIST_ERA_THRESHOLD
        and r_date.year - BUDDHIST_ERA_OFFSET == py_date.year
        and (r_date.month, r_date.day) == (py_date.month, py_date.day)
    )


# Kept as its own registry because both arms need it, and it has to be checked
# *before* the product entry-date causes: `python_out_of_window_date_preserved`
# would otherwise claim a converted cell, whose R side is genuinely outside the
# tracker window (ticket 61).
def _is_buddhist_era_conversion_row_order(m: CellMismatch) -> bool:
    """The conversion moved the row, so the ordinal now pairs two different rows.

    Product rows are aligned by position within (clinic_id, sheet), and R sorts
    an unconverted Buddhist-era date to the end of its group -- 2565-12-24 is
    later than every Gregorian date beside it. Python converts first and sorts
    2022-12-24 chronologically, three rows earlier, which displaces everything
    between. Verified on the real 254-tracker pair: 2022 Chiang Mai Maharaj
    Nakorn, sheet Dec22, "Accu-Chek Instant Test Strips" -- R's ordinal 11
    holds 2565-12-24 where Python holds 2022-12-28, and Python's ordinal 9
    holds the converted 2022-12-24.

    This is ``row_order_divergence`` with the conversion as its trigger, and it
    needs its own test because R's value is by construction absent from
    Python's group -- Python converted it -- so value membership cannot fire.
    """
    return m.era_shift_row_order_candidate


BUDDHIST_ERA_CONVERSION_CLASSIFIERS: dict[str, Classifier] = {
    "python_buddhist_era_converted": _is_python_buddhist_era_converted,
    "buddhist_era_conversion_row_order": _is_buddhist_era_conversion_row_order,
}

PATIENT_BUDDHIST_ERA_CLASSIFIERS: dict[str, Classifier] = BUDDHIST_ERA_CONVERSION_CLASSIFIERS | {
    "buddhist_era_typo": _is_buddhist_era_typo,
}


def _is_r_ymd_first_misparse(m: CellMismatch) -> bool:
    """R reads a ``D.M.YY`` source string year-first, swapping day and year.

    ``parse_date_string`` (r-archive/R/script2_helper_dates.R) calls
    ``lubridate::parse_date_time`` with ``orders = c("ymd", "dmy", "my")``.
    lubridate takes the first order that parses, and "30.1.18" parses fine as
    ymd -- year 30 -> 2030 -- so the dmy order is never reached. Every
    date the source writes with a two-digit year and a day that is not also a
    plausible-looking year lands on the wrong reading.

    Python is the correct side, on three independent grounds:

    * **Source.** 2018 Yangon Children's Hospital writes these dates as text
      inside the value cell -- ``Jan18!L92`` is ``10.3 (22.8.17)`` and
      ``Jan18!N92`` is ``223(30.1.18)``, day-first, matching Python's
      2017-08-22 and 2018-01-30 against R's 2022-08-17 and 2030-01-18.
    * **Impossibility.** R's reading puts 1,236 of the 1,714 affected cells in
      the *future* relative to the tracker's own year; Python's puts none
      there and lands 1,713 of them within three years of it.
    * **Out-of-range days.** Where the source day exceeds 12 (``31.5.16``),
      only the day-first reading is even well-formed as a date the clinic
      could have meant; R still produces 2031-05-16.

    The test is the digit swap itself -- same month, R's day is Python's
    two-digit year and vice versa -- and excludes the case where the two agree
    on the day, since a date whose day and year read alike (18.1.18) is
    parsed identically by both orders and so cannot be this cause.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    if r_date is None or py_date is None:
        return False
    if SENTINEL_DATE in (r_date, py_date):
        return False
    return (
        r_date.month == py_date.month
        and r_date.day == py_date.year % 100
        and r_date.year % 100 == py_date.day
        and r_date.day != py_date.day
    )


PATIENT_YMD_FIRST_CLASSIFIERS: dict[str, Classifier] = {
    "r_ymd_first_misparse": _is_r_ymd_first_misparse,
}


def _is_python_reads_bare_year(m: CellMismatch) -> bool:
    """A bare four-digit year in a date cell: Python reads the year, R the serial.

    Nine trackers type a year alone where the template asks for
    ``(dd-mmm-yyyy)`` -- 590 D.O.B. cells across four Yangon Children's
    trackers and 425 diagnosis dates across Sarawak, Uni Med Center, VNCH,
    Heart of Jesus and MMMHMC. Both pipelines used to read that number as an
    Excel serial, which lands in 1905; ``parse_date_flexible`` now resolves
    it as the year (ticket 52), so only R still does.

    Python is right, and the source says so rather than the shape of the diff:
    Sarawak General Hospital's **2024** workbook writes the same patients'
    diagnoses as real 1-January dates (``Patient List!G10`` is 2011-01-01 for
    MY_QJ001) where its 2025 and 2026 workbooks write the bare year, so the
    first of January is the clinic's own convention for a year with no day,
    and the recovered ages agree across the three years. R's reading has every
    such patient born or diagnosed in 1905, which drove ``age`` to the 999999
    sentinel and ``t1d_diagnosis_age`` negative.

    The test is the serial arithmetic itself: R's date must be exactly the
    Excel serial of the year Python read, which no coincidentally-1-January
    date can satisfy.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    if r_date is None or py_date is None:
        return False
    if (py_date.month, py_date.day) != (1, 1):
        return False
    return r_date == EXCEL_EPOCH + datetime.timedelta(days=py_date.year)


PATIENT_BARE_YEAR_CLASSIFIERS: dict[str, Classifier] = {
    "python_reads_bare_year": _is_python_reads_bare_year,
}


def _is_r_month_name_truncated_to_year(m: CellMismatch) -> bool:
    """A spelled-out month-year cell R keeps only the year of.

    ``parse_dates`` (script2_helper_patient_data_fix.R) shortens any word of
    four or more letters with ``sub("([[:alpha:]]{3})[[:alpha:]]", "\\\\1", date)``,
    which deletes the *fourth* letter and leaves the rest of the word standing:
    executed against R 4.5, "April-17" becomes "Aprl-17" and "August,2015"
    becomes "Augst,2015". Neither is a month lubridate recognises, so
    ``parse_date_time`` walks its order list down to the final ``"y"`` and
    returns 1 January of the year -- 2017-01-01 and 2015-01-01, which is
    exactly what R's frozen output carries for those cells.

    Python is right: ``parse_date_flexible``'s ``MONTH_NAME_PATTERN`` truncates
    the same names to a real abbreviation and its month-year branch resolves
    them to the first of the month the clinic actually wrote. Verified by
    running R's own truncation and order list over the source strings taken
    from the raw parquet (ticket 56), not inferred from the shape of the diff.

    The test is that R sits on 1 January of the same year Python read a
    later month for. Python landing on 1 January too is the bare-year cause
    above, and is excluded.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    if r_date is None or py_date is None:
        return False
    if (r_date.month, r_date.day) != (1, 1) or r_date.year != py_date.year:
        return False
    return py_date.day == 1 and py_date.month != 1


PATIENT_MONTH_NAME_TRUNCATED_CLASSIFIERS: dict[str, Classifier] = {
    "r_month_name_truncated_to_year": _is_r_month_name_truncated_to_year,
}


def _is_r_reads_day_as_month(m: CellMismatch) -> bool:
    """A month name R cannot read, so it reads the day number as the month.

    Once the alphabetic token fails, ``parse_date_time``'s order list reaches
    ``"my"``, which reads the two remaining numbers as month and year. The day
    is promoted to a month and the day itself is invented as the 1st: executed
    against R, "9-Dce-20" gives 2020-09-01, "11-Mach-20" gives 2020-11-01,
    "4-Okt-2023" gives 2023-04-01 and "10-MAC-2026" gives 2026-10-01 -- every
    one matching R's frozen output for that cell.

    The month names behind this are two dropped or transposed letters ("Dce",
    "ug"), R's own inability to keep "Mach" once truncation has run, and the
    Bahasa Malaysia spellings the Malaysian clinics write ("Mac", "Mei",
    "Okt"). Python is right on all of them: ``TYPO_REPLACEMENTS`` now maps each
    to its English abbreviation before parsing (ticket 56), so Python publishes
    the date the clinic wrote where R publishes a month it derived from the day.

    The test is that arithmetic identity -- R on the first of a month whose
    number is Python's day, in the same year.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    if r_date is None or py_date is None:
        return False
    if SENTINEL_DATE in (r_date, py_date):
        return False
    return r_date.day == 1 and r_date.year == py_date.year and py_date.day == r_date.month


def _is_r_parse_order_cannot_read_cell(m: CellMismatch) -> bool:
    """R sentinels because none of its eight parse orders fits the cell.

    The same mechanism as ``r_reads_day_as_month`` at the point where it runs
    out of road: with the month name unreadable, R's positional fallback needs
    the day to be a valid month number, so a day past 12 leaves the whole order
    list without a match and ``convert_to`` substitutes ERROR_VAL_DATE.
    Executed against R: "25-Mach-20" returns NA, as do "05/15/2026" and
    "Dec-22-2025" -- the month-first spellings no order in
    ``c("dmy","dmY","dbY","by","bY","mY","my","y")`` can express. Python reads
    all three.

    A day past 12 is the signature, and it is what separates this from the
    other reasons R sentinels a date. It is deliberately not applied to
    ``hospitalisation_date``, whose population round 6 measured as 100% clinical
    notes: R sentinels those because it cannot read a sentence, which is
    ticket 39's open question and not this cause.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    if r_date != SENTINEL_DATE or py_date is None or py_date == SENTINEL_DATE:
        return False
    return py_date.day > 12


PATIENT_UNREADABLE_MONTH_CLASSIFIERS: dict[str, Classifier] = {
    "r_reads_day_as_month": _is_r_reads_day_as_month,
    "r_parse_order_cannot_read_cell": _is_r_parse_order_cannot_read_cell,
}


def _is_age_from_bare_year(m: CellMismatch) -> bool:
    """An age derived from a date whose bare year only Python recovered.

    ``age`` comes from ``dob`` and ``t1d_diagnosis_age`` from ``dob`` plus
    ``t1d_diagnosis_date`` (``_fix_age``/``_fix_t1d_diagnosis_age``,
    clean/patient.py). Where one of those dates is a bare year (see
    ``python_reads_bare_year``), R derives from its 1905 reading and Python
    from the real one, so the two ages *must* differ -- R's lands around 113
    and its own 0-100 range check then stamps the 999999 sentinel.

    This is the same decided cause one step downstream, not a second one, so
    it is keyed on the mechanism: the row must itself carry a bare-year date
    mismatch. The derived values' shape alone (R sentinel, Python plausible)
    would also match a genuine age disagreement.
    """
    return m.row_has_bare_year_date


PATIENT_AGE_FROM_BARE_YEAR_CLASSIFIERS: dict[str, Classifier] = {
    "python_age_from_bare_year": _is_age_from_bare_year,
}


# No human has lived past 123, so a diagnosis age this large is not an age at
# all. Both populations that clear it decode as Excel serials to real dates --
# 20668 to 1956-08-01 and 42859 to 2017-05-04 -- confirmed in the source
# workbooks themselves (see source_date_in_diagnosis_age).
_MAX_PLAUSIBLE_AGE_YEARS = 130


def _numeric(value: Any) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None


def _is_r_never_derives_diagnosis_age(m: CellMismatch) -> bool:
    """Python computes a diagnosis age from the two dates; R never computes one.

    R's ``fix_t1d_diagnosis_age`` (script2_helper_patient_data_fix.R) exists
    and is unit-tested against exactly the strings the trackers carry -- "At
    birth", "4 months", "5y", "10y10m" -- but its **call site is commented
    out** (script2_process_patient_data.R:251, read directly). So R's
    ``t1d_diagnosis_age`` is only ever the source column put through
    ``as.numeric``: a blank cell stays NA, and a cell written in words becomes
    R's 999999 "recorded but invalid" sentinel. Python's
    ``_fix_t1d_diagnosis_age`` (clean/patient.py) fills from ``dob`` and
    ``t1d_diagnosis_date`` in exactly those two cases and otherwise keeps what
    the clinic recorded.

    Python is right, and the source says so rather than the shape of the diff.
    Where the source wrote the age in words, Python's derived figure agrees
    with the words: 2017 Mandalay's MM_QA010 reads "11yr" against a D.O.B. of
    2004-03-01 and a diagnosis of 2016-01-01, and Python derives 11; MM_QA011
    reads "4mth" against 2013-10-23 and 2014-02-01, and Python derives 0.
    Where the cell is blank, both pipelines hold the same two dates and only
    Python uses them -- 2024 Sarawak's MY_QJ001 (2000-06-30, 2011-01-01 on
    both sides) is null in R and 10 in Python. R keeps nothing a clinic
    recorded; Python recovers information R discards.

    The bare-year subset of this shape is already ``python_age_from_bare_year``
    (ticket 52), which fires only where the row's own date cells disagree. The
    rest of the population has no date mismatch at all, so it needs the
    mechanism stated directly.
    """
    if m.py_value is None:
        return False
    if m.r_value is None:
        return True
    r_numeric = _numeric(m.r_value)
    return r_numeric is not None and r_numeric == settings.error_val_numeric


def _is_source_date_in_diagnosis_age(m: CellMismatch) -> bool:
    """A date typed into the `Age at Diagnosis` column: R carries the serial.

    The template's ``Age at\\nDiagnosis*`` column is formula-derived, so most
    cells hold either a number or an Excel error string. Two clinics have a
    date sitting there instead, confirmed by reading the source workbooks:
    2023 Chiang Mai's Patient List row for TH_QB005 holds 1956-08-01 (serial
    20668) in a workbook whose ``Date of T1D Diagnosis`` column is empty for
    every patient, so its age formula reads ``#NUM!`` throughout; and 2023
    Yangon General's row for MM_QE043_YG holds 2017-05-04 (serial 42859)
    against a D.O.B. of 2008-01-01 and a diagnosis date of 2007-06-01 --
    a diagnosis a year before the birth.

    R's readxl reads the column as numeric and carries the raw serial into the
    age. Python's cast fails and the cell ends up null, which is the correct
    side: 20,668 is not an age, and no arithmetic recovers one here because
    the diagnosis date these clinics would need is itself missing or
    impossible. Both are source defects for ticket 40, not pipeline
    divergences to reconcile.

    The test is that R's value is too large to be an age, rather than that it
    decodes to a date -- an age column has no legitimate value in that range,
    and R's own 999999 sentinel is excluded because ``r_numeric_error_sentinel``
    owns it.
    """
    if m.py_value is not None:
        return False
    r_numeric = _numeric(m.r_value)
    if r_numeric is None or r_numeric == settings.error_val_numeric:
        return False
    return r_numeric > _MAX_PLAUSIBLE_AGE_YEARS


PATIENT_DIAGNOSIS_AGE_CLASSIFIERS: dict[str, Classifier] = {
    "r_never_derives_diagnosis_age": _is_r_never_derives_diagnosis_age,
    "source_date_in_diagnosis_age": _is_source_date_in_diagnosis_age,
}

# The three mg/dL readings R's fix_fbg manufactures from text
# (script2_helper_patient_data_fix.R:557-561, citing CDC's "getting tested"
# levels): high/bad/hi -> 200, med/medium -> 170, low/good/okay -> 140.
_R_FBG_CATEGORY_VALUES = frozenset({140.0, 170.0, 200.0})


def _is_r_fbg_text_category_invention(m: CellMismatch) -> bool:
    """R converts unreadable text into one of three invented glucose readings.

    ``fix_fbg`` (r-archive/R/script2_helper_patient_data_fix.R:551) runs its
    category patterns through ``grepl`` on the whole string with no word
    boundary, so any cell merely *containing* the letters wins a number. Two
    populations follow, and every one of the 85 affected cells was read back to
    its raw source value to confirm which:

    - 44 cells where the source is a category word or a phrase containing one.
      41 of them read ``Lost follow up`` and become **140**, because "fol-low"
      contains "low"; the other 3 are a genuine ``low``/``Low``. A patient lost
      to follow-up has no glucose reading at all, and R publishes one.
    - 41 cells where the source records a meter range or an out-of-range
      marker: ``SMBG 50-HI``, ``DSMP 250-HI``, ``129-HI``, ``CBG 57-High``,
      ``112/ High``, bare ``HI``. All become **200**, discarding the numeric
      endpoint the clinic did write. On a glucometer "HI" means a reading above
      the analytical ceiling -- far above 200 -- so R's substitution is not
      merely invented but wrong in direction.

    Python is the correct side and diverges here by design:
    ``_fix_fbg_column`` (clean/patient.py) implements the same CDC mapping but
    anchors each pattern to the full string (``^(low|good|okay)$``), so only a
    cell that says exactly "low" is treated as a category and everything else
    falls through to the numeric conversion and sentinels. The source cells are
    free text in a numeric column -- a defect for ticket 40, not a value to
    reconstruct.

    Keyed on R holding exactly one of the three invented constants while Python
    holds its numeric sentinel: Python only sentinels a cell it could not read
    at all, so a real reading of 200 cannot land in this shape.
    """
    r_numeric = _numeric(m.r_value)
    py_numeric = _numeric(m.py_value)
    return (
        r_numeric in _R_FBG_CATEGORY_VALUES
        and py_numeric is not None
        and py_numeric == settings.error_val_numeric
    )


def _is_r_unit_suffix_not_stripped(m: CellMismatch) -> bool:
    """The source writes the unit beside the reading; only Python reads past it.

    The 2018 trackers record updated FBG as ``148 mg/dl   (Mar-18)`` -- value,
    unit, and the date of the reading in one cell. Python strips the unit and
    lifts the parenthetical date out to ``fbg_updated_date``
    (``_fix_fbg_column`` and ``_extract_date_from_measurement``,
    clean/patient.py); R's ``fix_fbg`` handles neither, so ``as.numeric`` fails
    on the whole string and ``convert_to`` substitutes its sentinel.

    All 28 cells in this shape were read back to their raw source, and every
    one is a plain reading carrying its unit (three also carry no date:
    ``332 mg/dl``, ``196((Dec-2017)``). Python recovers a real measurement R
    throws away, so Python is the correct side.

    Keyed on the reverse of the invention shape above -- R sentinelled, Python
    holds a number -- which on this column is only reachable when R's parse
    failed and Python's did not.
    """
    r_numeric = _numeric(m.r_value)
    py_numeric = _numeric(m.py_value)
    return (
        r_numeric is not None
        and r_numeric == settings.error_val_numeric
        and py_numeric is not None
        and py_numeric != settings.error_val_numeric
    )


PATIENT_FBG_TEXT_CLASSIFIERS: dict[str, Classifier] = {
    "r_fbg_text_category_invention": _is_r_fbg_text_category_invention,
    "r_unit_suffix_not_stripped": _is_r_unit_suffix_not_stripped,
}

# A month sheet is named "Jan22", "Sept22" or "Oct'22" -- the trailing two
# digits are the tracker year, which is how the pipeline's own extraction
# derives tracker_year in the first place (get_tracker_year, R; the sheet-name
# year detection documented in docs/CLAUDE.md, Python).
_SHEET_YEAR = re.compile(r"(\d{2})\s*$")


def _sheet_year(m: CellMismatch) -> int | None:
    """The tracker year the mismatched row sits in, read off its sheet name.

    ``add_row_ordinal`` renames every key column to ``__key_<col>``, so the
    lookup matches on the suffix rather than on the bare name -- keying on
    ``sheet_name`` alone silently finds nothing and the cause never fires.
    """
    if not isinstance(m.key, dict):
        return None
    sheet = next(
        (v for k, v in m.key.items() if str(k).endswith("sheet_name") and isinstance(v, str)),
        None,
    )
    match = _SHEET_YEAR.search(sheet) if sheet else None
    return 2000 + int(match.group(1)) if match else None


def _is_python_rejects_beyond_tracker_year(m: CellMismatch) -> bool:
    """Python sentinels a date later than its tracker year; R keeps it.

    ``_validate_dates`` (clean/patient.py) replaces any date past 31 December
    of ``tracker_year`` with the error sentinel and logs an ``invalid_value``
    error against the patient. R has no equivalent guard -- ``grep`` over
    ``r-archive/R`` finds no future-date or tracker-year bound on any date
    column -- so R carries the impossible value into its output unchanged.
    (The docstring on ``_validate_dates`` claiming this "matches R pipeline
    behavior" is wrong, and is corrected as part of this ticket.)

    Python is the correct side, and the source says the value is genuinely
    impossible rather than merely surprising: 2022 Vietnam National Children's
    Hospital writes every one of its 43 ``Date of T1D Diagnosis`` cells as a
    2023 date (``Patient List!G13`` = 2023-07-16 for VN_QC001, born 2013-03,
    recruited 2017-07), so the workbook has patients diagnosed a year after
    the tracker was filled in and five years after they were recruited for
    having the disease. That is a defect in the workbook -- reported for
    [ticket 40] rather than inferred around -- and sentinelling it is the
    pipeline recognizing an unusable value, the same verdict
    ``buddhist_era_typo`` reached on an unusable year.

    Deliberately narrower than "Python sentinelled and R did not": where the
    raw cell holds free text Python's parser could not read at all (a
    misspelled month, a date buried in a clinical note), the mechanism is a
    parse failure rather than this guard, the verdict is not the same, and
    part of that population is still open as its own question.
    """
    tracker_year = _sheet_year(m)
    r_date = _as_date(m.r_value)
    return (
        tracker_year is not None
        and _as_date(m.py_value) == SENTINEL_DATE
        and r_date is not None
        and r_date != SENTINEL_DATE
        and r_date.year > tracker_year
    )


PATIENT_BEYOND_TRACKER_YEAR_CLASSIFIERS: dict[str, Classifier] = {
    "python_rejects_beyond_tracker_year": _is_python_rejects_beyond_tracker_year,
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

    Surviving parts are compared trimmed (ticket 50): Python trims each
    sub-value before merging -- ticket 46's separately-verified
    ``python_trims_merged_subvalue`` -- so where a source cell ends in a space
    the two causes stack in one cell and neither explained it alone. Trimming
    only ignores leading/trailing space per part, so an internal whitespace
    difference (``r_drops_richtext_space``) still falls through to its own
    cause.
    """
    if m.r_value is None or "NA" not in str(m.r_value):
        return False
    stripped = [p.strip() for p in str(m.r_value).split(",") if p.strip() not in ("NA", "")]
    py_parts = [] if m.py_value is None else str(m.py_value).split(",")
    return stripped == [p.strip() for p in py_parts if p.strip() != ""]


PATIENT_NA_UNITE_PADDING_CLASSIFIERS: dict[str, Classifier] = {
    "r_na_unite_padding": _is_r_na_unite_padding,
}


def _spaces_differ_only(m: CellMismatch) -> bool:
    if m.r_value is None or m.py_value is None:
        return False
    r_text, py_text = str(m.r_value), str(m.py_value)
    return r_text != py_text and r_text.replace(" ", "") == py_text.replace(" ", "")


def _is_r_drops_richtext_space(m: CellMismatch) -> bool:
    """R loses a space that Excel stores as a formatting run of its own.

    Where a cell's text carries mixed formatting, xlsx stores it as a
    rich-text shared string: a sequence of runs, each with its own font, and
    a space between two differently-formatted fragments becomes a run holding
    nothing but that space. openpyxl concatenates every run and reproduces the
    cell as Excel displays it; readxl drops the whitespace-only run.

    Verified in the source XML of two unrelated workbooks (ticket 46):

    - 2017 Yangon Children's Hospital, ``hba1c_updated``/``fbg_updated_mg``:
      ``<si><r>..<t>8.8</t></r><r>..<t xml:space="preserve"> </t></r><r>..
      <t>(20.9.16)</t></r></si>``. The same workbook also stores the identical
      text as a plain ``<si><t>8.8 (20.9.16)</t></si>`` for other patients,
      which R reads correctly -- which is why only some cells of the column
      diverge.
    - 2022 Mahosot, ``observations``: the same three-run shape around the
      space in "Unable to contact", the middle run recoloured.

    Python is the correct side: it reproduces the workbook. Fires only when
    the two values are identical once every space is removed *and* Python is
    the side holding more of them -- the opposite direction is a different
    cause (see ``python_trims_merged_subvalue``).
    """
    if not _spaces_differ_only(m):
        return False
    return str(m.py_value).count(" ") > str(m.r_value).count(" ")


PATIENT_RICHTEXT_SPACE_CLASSIFIERS: dict[str, Classifier] = {
    "r_drops_richtext_space": _is_r_drops_richtext_space,
}


def _is_python_trims_merged_subvalue(m: CellMismatch) -> bool:
    """Python trims each sub-value before joining a duplicate column group.

    Ticket 31 gave ``ColumnMapper.rename_columns`` a comma-join over the
    source columns that share one canonical name; it strips each fragment
    first, while R's ``tidyr::unite`` concatenates them exactly as read. So a
    source cell carrying a trailing space reaches R's output as
    "Normal ,Insulin" and Python's as "Normal,Insulin".

    Python is the correct side -- the space is inside the workbook's cell
    padding, not part of the recorded value, and the pipeline trims every
    string cell elsewhere. Requires the comma both sides carry, so an
    ordinary leading/trailing space (already handled by
    ``normalize_whitespace_column``) does not land here.
    """
    if not _spaces_differ_only(m):
        return False
    if "," not in str(m.py_value):
        return False
    return str(m.r_value).count(" ") > str(m.py_value).count(" ")


PATIENT_MERGED_SUBVALUE_TRIM_CLASSIFIERS: dict[str, Classifier] = {
    "python_trims_merged_subvalue": _is_python_trims_merged_subvalue,
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
        # Judged against the unit the column actually holds, which is not
        # always the one its name claims. Ticket 57 found six cells this could
        # not reach while the test went by name alone: 2020 Kantha Bopha's
        # fbg_baseline_mg is 90.1% sub-30, so the column is read as mmol/L and
        # its outliers 47.8 and 53.8 are rejected against the mmol ceiling --
        # while sitting well inside the mg/dL range. Round 10 measured the
        # obvious widening ("outside either unit") and backed it out, since it
        # would claim every genuinely-rejected mg/dL reading above 45. Ticket
        # 44 supplies the missing fact instead: column_unit_swapped comes from
        # the run's own glucose_unit_swapped records, so the bound is chosen on
        # evidence rather than on the column's name.
        #
        # A constant fix_fbg manufactured out of text is not a reading, so no
        # range has anything to say about it: r_fbg_text_category_invention
        # owns those, and without this guard the mmol bound would take five of
        # them off it purely because 140 exceeds 45.
        if r in _R_FBG_CATEGORY_VALUES:
            return False
        reads_as_mmol = m.column_unit_swapped or not m.column.endswith("_mg")
        low, high = (
            (MMOL_ANALYTICAL_MIN, MMOL_ANALYTICAL_MAX)
            if reads_as_mmol
            else (MG_ANALYTICAL_MIN, MG_ANALYTICAL_MAX)
        )
        return r < low or r > high

    for expected in (r * MMOL_TO_MG_FACTOR, r / MMOL_TO_MG_FACTOR):
        if abs(py - expected) <= max(1e-6, abs(expected) * 1e-4):
            return True
    return False


def _is_python_recovers_glucose_r_rejected(m: CellMismatch) -> bool:
    """The unit swap moves a reading across that R had already sentinelled.

    Ticket 57, one cell: 2022 Penang MY_QF004 Dec22 writes "-" in the mmol
    column and 9 in the mg one. R's converter turns the "-" into its numeric
    error value and stops there. Python's ``resolve_glucose_units`` finds that
    column 145/145 sub-30 -- so it is mmol throughout -- and moves the 9 into
    the mmol column, where it lands inside the advisor's analytical range.

    Python is the correct side: the clinic recorded a reading and R published
    an error code over it. Fires only where R holds the numeric error value and
    Python holds a reading the analytical limits accept, so it cannot claim a
    recovery the range check would itself have rejected.
    """
    if m.column not in GLUCOSE_UNIT_COLUMNS:
        return False
    r, py = _glucose_float(m.r_value), _glucose_float(m.py_value)
    if r != settings.error_val_numeric or py is None:
        return False
    low, high = (
        (MG_ANALYTICAL_MIN, MG_ANALYTICAL_MAX)
        if m.column.endswith("_mg")
        else (MMOL_ANALYTICAL_MIN, MMOL_ANALYTICAL_MAX)
    )
    return low <= py <= high


PATIENT_GLUCOSE_UNIT_CLASSIFIERS: dict[str, Classifier] = {
    "python_glucose_unit_corrected": _is_python_glucose_unit_corrected,
    "python_recovers_glucose_r_rejected": _is_python_recovers_glucose_r_rejected,
}

_MMOL_GLUCOSE_COLUMNS = frozenset(mmol_col for _, mmol_col in GLUCOSE_COLUMN_PAIRS)


def _carries_a_reading(value: Any) -> bool:
    """Did this side publish a glucose measurement in this cell at all?"""
    reading = _glucose_float(value)
    return reading is not None and reading != settings.error_val_numeric


def _restates_its_own_mg_cell(mmol_value: Any, mg_value: Any) -> bool:
    """Is this side's mmol cell nothing but its own mg cell in mmol/L?

    A side that published nothing here -- null, or its numeric sentinel --
    trivially added no reading of its own. A side that did publish one has to
    be the exact 18-fold image of the mg cell it sits beside; anything else is
    a measurement the mg cell cannot account for.
    """
    if not _carries_a_reading(mmol_value):
        return True
    mmol = _glucose_float(mmol_value)
    if not _carries_a_reading(mg_value) or mmol is None:
        return False
    mg = _glucose_float(mg_value)
    assert mg is not None
    expected = mg / MMOL_TO_MG_FACTOR
    return abs(mmol - expected) <= max(1e-6, abs(expected) * 1e-4)


def _is_mmol_derived_from_mg_sibling(m: CellMismatch) -> bool:
    """The mmol cell restates a divergence its mg sibling already carries.

    Neither pipeline reads the mmol column from the workbook independently:
    both derive it from the mg cell beside it (``convert_glucose_units``,
    clean/patient.py; ``fix_fbg``'s ``fbg/18`` in R). So when the two sides
    disagree about the mg cell, they disagree about the mmol cell as an
    arithmetic consequence, and the mmol difference is not a second finding.

    Measured over the whole 254-tracker run, all 2,935 cells in this shape sat
    beside an mg cell that was itself a mismatch with an already-named cause --
    not one exception -- in three populations:

    - **2,797** where ticket 42's unit swap moved a reading into a column R
      never populated (2025 Kantha Bopha II KH_QD097: the source writes 14.4
      under the mg/dL header; R keeps mg=14.4 and no mmol, Python moves it to
      mmol and rescales mg to 259.2).
    - **110** where R derived mmol from an mg reading Python refused -- either
      one ``fix_fbg`` invented out of text (140 from "Lost follow up") or one
      beyond the analytical ceiling (2013 mg/dL, which R publishes as 111.8
      mmol/L, above the level the medical advisor called impossible).
    - **28** the other way round, where R sentinelled an mg cell carrying its
      unit ("148 mg/dl   (Mar-18)") and Python read it and derived 8.22.

    Python is the correct side in all three; each is already argued under the
    mg cell's own cause, which is why this one names the cascade rather than
    re-deciding it. Bounded two ways so it cannot swallow a genuine mmol
    divergence: the mg sibling must itself disagree, and each side's mmol value
    must be either absent or exactly its own mg cell divided by 18.
    """
    if m.column not in _MMOL_GLUCOSE_COLUMNS or m.mg_sibling is None:
        return False
    r_mg, py_mg = m.mg_sibling
    if not _values_differ(r_mg, py_mg):
        return False
    if not _restates_its_own_mg_cell(m.r_value, r_mg):
        return False
    if not _restates_its_own_mg_cell(m.py_value, py_mg):
        return False
    return _carries_a_reading(m.r_value) or _carries_a_reading(m.py_value)


PATIENT_GLUCOSE_CASCADE_CLASSIFIERS: dict[str, Classifier] = {
    "mmol_derived_from_mg_sibling": _is_mmol_derived_from_mg_sibling,
}


_HBA1C_RANGE_COLUMNS = ("hba1c_baseline", "hba1c_updated")


def _is_python_rejects_out_of_range_hba1c(m: CellMismatch) -> bool:
    """A glucose reading typed into the HbA1c column.

    Ticket 57, eight cells across 2024 Preah Kossamak and two other clinics:
    the source holds 240, 299 and 125 where an HbA1c percentage belongs. R has
    no range check on this column and publishes the number as an HbA1c; Python
    fails it against the bound ``reference_data/validation_rules.yaml`` declares
    and stamps the numeric sentinel.

    Python is the correct side -- an HbA1c of 240% is not a measurement, and
    publishing it would carry a fasting-glucose reading into the HbA1c series.
    The bound is read from the config rather than restated, so the classifier
    cannot drift from the rule that produced the rejection. Each cell is also a
    source defect for ticket 40: the number itself is real, it is in the wrong
    column.
    """
    if m.column not in _HBA1C_RANGE_COLUMNS:
        return False
    ceiling = load_numeric_ranges().get(m.column, {}).get("max")
    if ceiling is None:
        return False
    r, py = _numeric(m.r_value), _numeric(m.py_value)
    if r is None or py != settings.error_val_numeric:
        return False
    return r > ceiling


PATIENT_HBA1C_RANGE_CLASSIFIERS: dict[str, Classifier] = {
    "python_rejects_out_of_range_hba1c": _is_python_rejects_out_of_range_hba1c,
}


def _is_python_declines_unreconstructable_date(m: CellMismatch) -> bool:
    """R publishes a date from a token damaged past reading; Python refuses.

    The other face of ``r_parse_order_cannot_read_cell``. Round 9 established by
    running R 4.5 that ``parse_dates`` cannot fail quietly: it deletes the fourth
    letter of any long word and then walks a fixed order list ending in ``my``
    and ``y``, so *something* comes back for almost any input. Where the source
    cell is damaged in a way no reading can be recovered from, that something is
    an invention.

    Ticket 57 measured 37 such cells and none is reconstructable:

    - ``25-Ma4-2025`` (18 cells, 2025 Taunggyi) -- "Ma4" is Mar or May and the
      workbook says neither; R reads the embedded 4 as the month and publishes
      2025-04-25, an answer neither spelling supports.
    - a separator swallowed or a digit group glued (``26/102022``, ``8/1023``,
      ``3/10.23``, ``10-Oct-2-24``, ``13-Mar-0202``) -- where the missing
      separator goes is a guess, and R's own answer is not stable: its frozen
      output reads ``10/1023`` as 2010-10-23 while running its own parser over
      that string in isolation returns 2023-10-10.
    - ``e.g. xxx (mth-18)`` (2018 Penang DC) -- the tracker template's own
      example text left in a patient row, which R turns into 2018-01-01.

    Python is the correct side of all three: declining to publish a date the
    source does not determine is right, and every cell here is a finding for
    ticket 40 rather than something to infer. The test is the direction alone --
    R on a real date, Python on the sentinel -- so it is wired only to the date
    columns whose other causes are already classified ahead of it.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    if r_date is None or py_date != SENTINEL_DATE:
        return False
    return r_date != SENTINEL_DATE


PATIENT_UNRECONSTRUCTABLE_DATE_CLASSIFIERS: dict[str, Classifier] = {
    "python_declines_unreconstructable_date": _is_python_declines_unreconstructable_date,
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
    unit_swapped_columns: dict[str, set[str]] | None = None,
    tracker_year_col: str | None = None,
) -> DirectoryComparison:
    numeric_cols = numeric_cols or []
    unit_swapped_columns = unit_swapped_columns or {}
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
                cell_mismatches=compare_cells(
                    r_df,
                    py_df,
                    key_cols,
                    order_group_cols,
                    unit_swapped_columns.get(name),
                    tracker_year_col,
                ),
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
    row_key_unmatched_rows = []
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

        # An unmatched row never reaches a cell comparison, so unless its key is
        # named here it appears nowhere else in the report (ticket 47).
        for side, keys in (
            ("R only", file_comparison.row_key_overlap.r_only_keys),
            ("Python only", file_comparison.row_key_overlap.py_only_keys),
        ):
            for key, surplus in keys:
                row_key_unmatched_rows.append(
                    {
                        "file": name,
                        "side": side,
                        "key": " | ".join(str(part) for part in key),
                        "rows": surplus,
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
        "row_key_unmatched": row_key_unmatched_rows,
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


def _is_python_reads_date_in_clinical_note(m: CellMismatch) -> bool:
    """R cannot read a sentence, so it sentinels; Python reads the date it states.

    ``hospitalisation_date``'s header is free text -- "Hospitalisation due to
    diabetes emergency or glucose control (Include Date)", read directly from
    2021 Preah Kossamak's ``Feb21`` sheet -- so clinicians write a case note and
    put the date inside it. Round 6 measured the column's whole residual as
    100% clinical notes.

    R's ``parse_dates`` hands the string to a fixed order list and gives up,
    stamping ERROR_VAL_DATE. Python scans it for an anchored day/month/year
    shape (``recover_date_from_text``, clean/date_parser.py) and publishes the
    first date the note names. Python is the correct side: the date is legibly
    present -- "DKA 23 Oct 2020", "Passed away 28/10/2019 due to DKA" -- and
    discarding it loses a hospitalisation the clinic recorded.

    The recogniser refuses rather than guesses, which is what keeps this cause
    honest: a cell carrying numbers and no date ("3 month come back meet
    Doctor", 48 cells) yields nothing and stays sentinelled on both sides.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    return r_date == SENTINEL_DATE and py_date is not None and py_date != SENTINEL_DATE


def _is_note_dates_read_differently(m: CellMismatch) -> bool:
    """Both pipelines find a date in the note and pick different ones.

    Four shapes, all traced to their source strings on the real 254-tracker set
    and all resolving in Python's favour:

    - **A stay's two endpoints.** "DKA: admitted 6-12 Nov 2020" -> R reads the
      range's two numbers as a day and a month (2020-12-06); Python takes the
      admission day the note's own month gives it (2020-11-06).
    - **A day read as a year.** "26 Jun (ceton urine high)" -> R returns
      2026-01-01; Python resolves 26 June against the tracker's year.
    - **A note listing several admissions.** "Dec 2019, Mar 2020 DKA Jan 2021
      DKA" -> R composes 2019-03-20 out of fragments of all three; Python
      publishes the first, and logs ``date_multiple_in_cell`` so the discard is
      visible.
    - **A range with no separators at all.** "25Jul-2Aug2022" (1 cell) is the
      one shape neither side reads correctly: R gives 2022-02-25 and Python
      2022-08-02, the discharge day, because the missing separator makes the
      opening "25Jul" indistinguishable from a token with an unreadable year.
      The source is what needs correcting, and it is reported for that.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    if r_date is None or py_date is None:
        return False
    return SENTINEL_DATE not in (r_date, py_date) and r_date != py_date


def _is_r_invents_january_from_bare_year(m: CellMismatch) -> bool:
    """The note names a year and no month; R publishes 1 January, Python refuses.

    "DKA 2019" and "DKA 2020: June, Aug, Nov" (24 cells across two trackers).
    R's parse order list ends in ``y``, so a four-digit number anywhere in the
    string becomes 1 January of that year -- which the second example shows to
    be plainly wrong, since the note says the admissions were in June, August
    and November.

    Python refuses: a month cannot be recovered from anything in the cell, and
    the whole-cell bare-year convention (``python_reads_bare_year``, ticket 52)
    rests on a clinic writing *only* a year, which is not this. The sentinel is
    the honest reading -- something was written, and it is not a date.
    """
    r_date, py_date = _as_date(m.r_value), _as_date(m.py_value)
    if py_date != SENTINEL_DATE or r_date is None or r_date == SENTINEL_DATE:
        return False
    return r_date.month == 1 and r_date.day == 1


PATIENT_CLINICAL_NOTE_CLASSIFIERS: dict[str, Classifier] = {
    "python_reads_date_in_clinical_note": _is_python_reads_date_in_clinical_note,
    "note_dates_read_differently": _is_note_dates_read_differently,
    "r_invents_january_from_bare_year": _is_r_invents_january_from_bare_year,
}
