"""Product data cleaning pipeline.

Mirrors ``clean/patient.py`` architecture: a single orchestrator
(``clean_product_data``) dispatches to step-scoped private helpers. Covers
R Script 2 steps 2.1-2.22.
"""

from pathlib import Path

import polars as pl

from a4d.clean.converters import parse_date_column, safe_convert_column
from a4d.clean.schema_product import apply_schema, get_product_data_schema, get_string_columns
from a4d.config import settings
from a4d.errors import ErrorCollector
from a4d.reference.products import load_known_products, load_product_categories

ACTIVITY_COLS: tuple[str, ...] = (
    "product_entry_date",
    "product_units_received",
    "product_received_from",
    "product_units_released",
    "product_released_to",
    "product_units_returned",
    "product_returned_by",
)

UNIT_COLS: tuple[str, ...] = (
    "product_units_received",
    "product_units_released",
    "product_units_returned",
)

EMPTY_ROW_COLS: tuple[str, ...] = (
    "product_units_received",
    "product_units_released",
    "product_units_returned",
    "product_released_to",
    "product_entry_date",
    "product_balance",
)

# Buddhist Era / Common Era disambiguation point. Mandalay trackers carry
# Buddhist-era dates (BE = CE + 543); a parsed year >= 2400 is implausibly
# Gregorian and treated as either Buddhist-era or already-sentinel
# (error_val_date 9999-09-09). _validate_entry_dates skips these so they
# flow through unchanged, matching R, while still flagging fat-finger
# Gregorian futures (e.g. 2099 in a 2024 tracker).
BUDDHIST_ERA_THRESHOLD: int = 2400

# Lower-bound year guard for _validate_entry_dates. A parsed Gregorian
# year more than YEAR_FLOOR_DELTA years before the tracker's calendar
# year is implausible (start-balance backfill is months-to-a-few-years,
# not decades) and almost certainly a tiny-int Excel-serial mis-coercion
# (e.g. a raw cell holding `29` parsing to 1900-01-29).
YEAR_FLOOR_DELTA: int = 5

# End-of-block summary-row residue scrub for product_entry_date. Two flavours
# observed in the corpus, both junk written into the date column between
# product sub-blocks: (1) literal marker strings, (2) tiny ints typed as a
# day-of-month into the wrong row (e.g. "30" in 2025 NPH row 81). Nulled
# before parse_date_flexible runs so the cleaned output is NULL rather than
# 9999-09-09 (parse-failure sentinel) or 1900-01-29 (Excel-leap-year-bug
# artefact). Product-only — patient pipeline must stay untouched.
PRODUCT_DATE_NA_MARKERS: frozenset[str] = frozenset({"amount left"})

# Excel serial for 2000-01-01. A4D trackers are 2017+, so a strict floor would
# be 42736 (2017-01-01); 36526 is deliberately looser to leave a ~17-year buffer
# that _validate_entry_dates handles via YEAR_FLOOR_DELTA. The scrub here only
# needs to catch unambiguous residue (raw day-of-month ints landing as
# 1900-0X-XX via Excel's leap-year bug); legitimate-looking but out-of-range
# serials are left for the year-floor check so they show up in the audit log.
MIN_PLAUSIBLE_EXCEL_SERIAL: int = 36526


def clean_product_data(
    df_raw: pl.DataFrame,
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """Clean raw product data through the full R Script 2 sequence.

    Executes steps 2.1-2.22 in order and returns a DataFrame conforming to
    the product meta schema defined in ``clean/schema_product.py``.

    Args:
        df_raw: Raw product DataFrame from extraction.
        error_collector: Accumulator for row-level data quality errors.

    Returns:
        Cleaned product DataFrame.
    """
    df = _normalize_empty_strings_to_null(df_raw)  # 2.0 (see helper docstring)
    df = _split_multi_product_cells(df)           # 2.1
    df = _switch_misplaced_columns(df)            # 2.3
    df = _remove_uninformative_rows(df)           # 2.4
    df = _add_row_index(df)                       # 2.5
    df = _format_dates(df, error_collector)       # 2.6
    _check_entry_dates_match_sheet(df, error_collector)  # 2.6a (R-parity log)
    df = _validate_entry_dates(df, error_collector)  # 2.6b
    df = _fill_product_names_and_sort(df)         # 2.7
    df = _extract_balance_from_received(df)       # 2.8
    df = _recode_na_units_to_zero(df)             # 2.9
    df = _clean_received_from(df)                 # 2.10
    df = _clean_units_received(df, error_collector)  # 2.11
    df = _recode_na_units_to_zero(df)             # 2.12
    df = _remove_empty_data_rows(df)              # 2.13
    df = _compute_balance_status(df)              # 2.14
    df = _compute_running_balance(df)             # 2.15

    # 2.16 — type cast numeric/date columns via ErrorCollector; strip strings
    # so trailing whitespace from openpyxl matches R's readxl trim-on-read.
    # No string->Int intermediate needed (cf. patient pipeline's Int32-via-Float64
    # path): product unit columns are Float64 by schema, and the only Int columns
    # (product_table_year/month) arrive from extraction as numeric, not strings.
    schema = get_product_data_schema()
    cast_targets = (pl.Int32, pl.Int64, pl.Float32, pl.Float64, pl.Date)
    for col, target in schema.items():
        if col not in df.columns or target not in cast_targets:
            continue
        if df.schema[col] == target:
            continue
        df = safe_convert_column(df, col, target, error_collector)

    string_cols = [c for c in get_string_columns() if c in df.columns]
    if string_cols:
        df = df.with_columns([pl.col(c).str.strip_chars() for c in string_cols])

    # 2.17 — drop helper index column added in 2.5.
    if "index" in df.columns:
        df = df.drop("index")

    df = _validate_negative_balances(df, error_collector)  # 2.18
    df = _report_unknown_products(df, error_collector)     # 2.19
    df = _add_product_categories(df)                       # 2.20
    df = _extract_unit_capacity(df)                        # 2.21
    # 2.22 cross-month combine happens at the table stage (S4-T1), not here.

    # Final schema conformance: guarantees 19 columns in schema order.
    df = apply_schema(df)
    # R-parity: UNIT_COLS treat absence as 0 (helper_product_data.R:292-297),
    # so re-run the recode after schema seeding fills any newly-added column.
    return _recode_na_units_to_zero(df)


def clean_product_file(
    raw_parquet_path: Path,
    output_parquet_path: Path,
    error_collector: ErrorCollector | None = None,
) -> None:
    """Clean a single product parquet file (I/O wrapper).

    Reads the raw parquet, runs ``clean_product_data``, and writes the result
    to the output path. Mirrors ``clean_patient_file``.

    Args:
        raw_parquet_path: Raw product parquet produced by extraction.
        output_parquet_path: Destination for the cleaned parquet.
        error_collector: Optional ErrorCollector; a new one is created if None.
    """
    ec = error_collector if error_collector is not None else ErrorCollector()
    df_raw = pl.read_parquet(raw_parquet_path)
    df_clean = clean_product_data(df_raw, ec)
    df_clean.write_parquet(output_parquet_path)


def _normalize_empty_strings_to_null(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.0 — coerce "" / whitespace-only string cells to null.

    R's readxl returns NA for blank Excel cells; openpyxl returns an empty
    string. Without this normalisation, rows whose only content is an empty
    string survive `_remove_uninformative_rows` and `_remove_empty_data_rows`
    (observed on 2024 CDA Dec24, which has one such row in
    product_units_received).
    """
    exprs = [
        pl.when(pl.col(c).str.strip_chars() == "")
        .then(None)
        .otherwise(pl.col(c))
        .alias(c)
        for c, dtype in df.schema.items()
        if dtype == pl.String
    ]
    return df.with_columns(exprs) if exprs else df


def _split_multi_product_cells(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.1 — split cells containing multiple products.

    Splits the ``product`` column on "; " and " and ". Parenthesized unit
    hints (e.g. "Product A (1 box)") are extracted into ``product_units_notes``
    and the numeric quantity is routed to ``product_units_received`` or
    ``product_units_released`` based on which side has a counterparty.
    """
    if "product" not in df.columns:
        return df

    df = df.with_columns(
        pl.col("product").cast(pl.Utf8).str.replace_all(" and ", "; ").alias("product")
    )
    df = df.with_columns(pl.col("product").str.split("; ")).explode("product")

    if "product_units_notes" not in df.columns:
        df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias("product_units_notes"))
    else:
        df = df.with_columns(pl.col("product_units_notes").cast(pl.Utf8))

    for col in ("product_units_received", "product_units_released"):
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Utf8))
        else:
            df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(col))

    product = pl.col("product").cast(pl.Utf8)
    has_paren_and_kw = (
        product.str.contains(r"\(")
        & product.str.contains(r"\)")
        & (product.str.contains("box") | product.str.contains("unit"))
    )
    no_slash = ~product.str.contains("/")

    paren_text = product.str.extract(r"\(([^()]+)\)", 1)
    # Deliberate deviation from R (helper_product_data.R:579,594): R uses
    # "[1-9]+" which drops the leading digit of counts containing 0
    # (e.g. "(10 box)" -> "1"). No real tracker row currently triggers
    # box/unit extraction, but "\d+" is the correct regex.
    number_str = paren_text.str.extract(r"(\d+)", 1)

    df = df.with_columns(
        pl.when(has_paren_and_kw)
        .then(paren_text)
        .otherwise(pl.col("product_units_notes"))
        .alias("product_units_notes")
    )

    if "product_received_from" in df.columns:
        df = df.with_columns(
            pl.when(
                has_paren_and_kw
                & no_slash
                & pl.col("product_received_from").is_not_null()
            )
            .then(number_str)
            .otherwise(pl.col("product_units_received"))
            .alias("product_units_received")
        )

    if "product_released_to" in df.columns:
        df = df.with_columns(
            pl.when(
                has_paren_and_kw
                & no_slash
                & pl.col("product_released_to").is_not_null()
            )
            .then(number_str)
            .otherwise(pl.col("product_units_released"))
            .alias("product_units_released")
        )

    return df


def _switch_misplaced_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.3 — swap ``product_units_received`` with ``product_received_from``
    for each sheet that contains "Remaining Stock" in units_received.

    Observed in 2018 PNG Nov/Dec trackers. R applies this rename inside its
    per-sheet loop (read_product_data.R:577); Python's clean pipeline
    operates on the whole-file DataFrame, so we scope the swap with .over()
    to avoid corrupting clean sheets in the same file.
    """
    if (
        "product_units_received" not in df.columns
        or "product_received_from" not in df.columns
        or "product_sheet_name" not in df.columns
    ):
        return df

    has_remaining_in_sheet = (
        pl.col("product_units_received")
        .cast(pl.Utf8)
        .str.contains("Remaining Stock")
        .any()
        .over("product_sheet_name")
    )

    if not df.select(has_remaining_in_sheet.any()).item():
        return df

    return df.with_columns(
        pl.when(has_remaining_in_sheet)
        .then(pl.col("product_received_from"))
        .otherwise(pl.col("product_units_received"))
        .alias("product_units_received"),
        pl.when(has_remaining_in_sheet)
        .then(pl.col("product_units_received"))
        .otherwise(pl.col("product_received_from"))
        .alias("product_received_from"),
    )


def _remove_uninformative_rows(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.4 — drop rows where every activity column is null."""
    existing = [c for c in ACTIVITY_COLS if c in df.columns]
    if not existing:
        return df
    all_null = pl.all_horizontal([pl.col(c).is_null() for c in existing])
    return df.filter(~all_null)


def _add_row_index(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.5 — add a 1-based ``index`` column matching R's ``seq(1, nrow)``."""
    return df.with_row_index("index", offset=1)


def _null_entry_date_residues(df: pl.DataFrame) -> pl.DataFrame:
    """Pre-clean for step 2.6 — null end-of-block summary-row residue cells.

    Two patterns observed between product sub-blocks in tracker source files,
    both nulled before any date parsing runs:

    1. Marker strings (case-insensitive, whitespace-trimmed) listed in
       ``PRODUCT_DATE_NA_MARKERS``. Currently only ``"Amount Left"`` —
       observed in 2018 Mahosot Nov18/Dec18, six per sheet between sub-blocks.
       Add more only after a corpus sweep finds them.
    2. Tiny Excel serials below ``MIN_PLAUSIBLE_EXCEL_SERIAL`` (2000-01-01).
       Catches stray day-of-month integers typed into the wrong row
       (e.g. raw ``30`` in 2025 NPH row 81 → 1900-01-29 via the pre-Mar-1900
       leap-year-bug epoch).

    Without this scrub the residue surfaces in cleaned output as either
    ``9999-09-09`` (parse-failure sentinel for "Amount Left") or
    ``1900-01-29`` (Excel-leap-year-bug artefact for tiny serials). Both
    are junk; nulling at source makes the output match R semantics
    (which silently NA-coerces) for the marker case, and produces cleaner
    data than R for the tiny-serial case.
    """
    if "product_entry_date" not in df.columns:
        return df

    raw = pl.col("product_entry_date").cast(pl.Utf8).str.strip_chars()
    is_marker = raw.str.to_lowercase().is_in(list(PRODUCT_DATE_NA_MARKERS))
    as_num = raw.cast(pl.Float64, strict=False)
    is_tiny_serial = (
        as_num.is_not_null()
        & (as_num > 0)
        & (as_num < MIN_PLAUSIBLE_EXCEL_SERIAL)
    )

    return df.with_columns(
        pl.when(is_marker | is_tiny_serial)
        .then(pl.lit(None, dtype=pl.Utf8))
        .otherwise(pl.col("product_entry_date").cast(pl.Utf8))
        .alias("product_entry_date")
    )


def _format_dates(
    df: pl.DataFrame, error_collector: ErrorCollector
) -> pl.DataFrame:
    """Step 2.6 — parse ``product_entry_date`` with the flexible date parser.

    Three preprocessing steps run before delegating to ``parse_date_column``:

    1. Null end-of-block summary-row residue (marker strings and
       tiny-int Excel serials) via ``_null_entry_date_residues``, so they
       become NULL in the cleaned output instead of the parse-failure
       sentinel or 1900-01-29 Excel-leap-year artefacts.
    2. Strip a trailing time component (``" HH:MM[:SS]"``) from Excel
       datetimes cast to string. Uses a precise regex rather than splitting
       on the first space, so date strings that legitimately contain
       spaces (e.g. ``"24 Feb 2020"``) survive intact.
    3. Normalize separator typos observed in the corpus (2026-04-29):
       ``"--"`` → ``"-"``, period-then-letter → space, underscore → space.
       Each rule is unambiguous and does not collide with valid date
       formats. Product-scoped only; ``parse_date_flexible`` is shared
       with the patient pipeline and is not modified.
    """
    if "product_entry_date" not in df.columns:
        return df
    if df.schema["product_entry_date"] == pl.Date:
        return df
    df = _null_entry_date_residues(df)
    df = df.with_columns(
        pl.col("product_entry_date")
        .cast(pl.Utf8)
        .str.replace(r"\s+\d{1,2}:\d{2}(:\d{2})?$", "")
        .str.replace_all(r"-{2,}", "-")
        .str.replace_all(r"(\d)\.([A-Za-z])", r"$1 $2")
        .str.replace_all(r"_", " ")
        .alias("product_entry_date")
    )
    return parse_date_column(
        df, "product_entry_date", error_collector, patient_id_col="product"
    )


def _check_entry_dates_match_sheet(
    df: pl.DataFrame, error_collector: ErrorCollector
) -> None:
    """R-parity warning for entry dates that disagree with the sheet header.

    Mirrors R's ``check_entry_dates`` (read_product_data.R): one log entry
    per row where the parsed ``product_entry_date`` doesn't match
    ``(product_table_year, product_table_month)``. Sentinels, nulls, and
    Buddhist-era dates are skipped.

    R filters to numeric Excel-serial cells before checking; Python checks
    every parsed date because ``parse_date_flexible`` accepts both serials
    and text. This is a deliberate parity-or-better expansion — the integration
    diff harness tolerates the row-count drift.

    Side-effecting only: pushes log entries; never mutates ``df``.
    """
    needed = {"product_entry_date", "product_table_year", "product_table_month"}
    if not needed.issubset(df.columns):
        return

    error_date = pl.lit(settings.error_val_date).str.to_date()
    table_year = pl.col("product_table_year").cast(pl.Int32, strict=False)
    table_month = pl.col("product_table_month").cast(pl.Int32, strict=False)

    is_real_date = (
        pl.col("product_entry_date").is_not_null()
        & (pl.col("product_entry_date") != error_date)
        & (pl.col("product_entry_date").dt.year() < BUDDHIST_ERA_THRESHOLD)
    )
    mismatch = (pl.col("product_entry_date").dt.month() != table_month) | (
        pl.col("product_entry_date").dt.year() != table_year
    )

    select_cols = [
        "file_name" if "file_name" in df.columns else pl.lit("unknown").alias("file_name"),
        "product" if "product" in df.columns else pl.lit("unknown").alias("product"),
        "product_entry_date",
        table_year.alias("_table_year"),
        table_month.alias("_table_month"),
        "product_sheet_name" if "product_sheet_name" in df.columns
        else pl.lit("unknown").alias("product_sheet_name"),
    ]
    offenders = df.filter(is_real_date & mismatch).select(select_cols)

    for file_name, product, entry_date, ty, tm, sheet_name in offenders.iter_rows():
        error_collector.add_error(
            file_name=file_name or "unknown",
            patient_id=product or "unknown",
            column="product_entry_date",
            original_value=str(entry_date),
            error_message=(
                f"product_entry_date {entry_date} does not match sheet "
                f"'{sheet_name or 'unknown'}' (expected {ty}-{tm:02d})"
            ),
            error_code="invalid_value",
            function_name="check_entry_dates",
        )


def _validate_entry_dates(
    df: pl.DataFrame, error_collector: ErrorCollector
) -> pl.DataFrame:
    """Step 2.6b — flag fat-fingered Gregorian entry dates outside the tracker window.

    A row is flagged when its parsed Gregorian year falls outside
    ``[product_table_year - YEAR_FLOOR_DELTA, product_table_year]`` and is below
    ``BUDDHIST_ERA_THRESHOLD``. Two divergence patterns are caught, handled
    asymmetrically:

    * **Above-max** (future-year typos, e.g. ``2099-03-15`` in a 2024 tracker):
      logged AND replaced with ``error_val_date`` (9999-09-09). Future dates are
      genuinely ambiguous (premature next-month entry vs typo); the sentinel
      preserves that uncertainty signal in the output.
    * **Below-min** (year-floor, e.g. ``1967-02-05`` in a 2024 tracker, or raw
      cell ``29`` → 1900-01-29 from Excel-serial mis-coercion): logged ONLY;
      the parsed date is preserved. Year-floor cells are unambiguously bad data
      (1900-2014 in 2020+ trackers). R does not validate — leaving the parsed
      date in place aligns the downstream sort/cumsum trajectory with R while
      the audit log retains the data-quality flag.

    Above/below cases are logged with distinct messages so triage in
    ``table_error_messages.parquet`` can distinguish them.

    Years at or beyond ``BUDDHIST_ERA_THRESHOLD`` (2400) are left untouched on both
    branches so Buddhist-era dates (e.g. ``2567-11-11`` from Mandalay trackers)
    flow through, and the parse-failure sentinel (9999-09-09) is not re-clobbered
    or double-logged. This deliberately diverges from the patient pipeline's
    ``_validate_dates``, which still clobbers any future date — patient is
    out of scope for this change.
    """
    if "product_entry_date" not in df.columns or "product_table_year" not in df.columns:
        return df

    error_date = pl.lit(settings.error_val_date).str.to_date()
    table_year = pl.col("product_table_year").cast(pl.Int32)
    max_valid = pl.date(table_year, 12, 31)
    min_valid = pl.date(table_year - YEAR_FLOOR_DELTA, 1, 1)

    not_buddhist = pl.col("product_entry_date").dt.year() < BUDDHIST_ERA_THRESHOLD
    above_max_mask = (
        pl.col("product_entry_date").is_not_null()
        & (pl.col("product_entry_date") > max_valid)
        & not_buddhist
    )
    below_min_mask = (
        pl.col("product_entry_date").is_not_null()
        & (pl.col("product_entry_date") < min_valid)
        & not_buddhist
    )

    above = df.filter(above_max_mask).select(
        "file_name", "product", "product_entry_date", "product_table_year", "product_sheet_name"
    )
    for file_name, product, entry_date, table_year_val, sheet_name in above.iter_rows():
        error_collector.add_error(
            file_name=file_name or "unknown",
            patient_id=product or "unknown",
            column="product_entry_date",
            original_value=str(entry_date),
            error_message=(
                f"product_entry_date {entry_date} beyond "
                f"product_table_year {table_year_val} "
                f"(sheet '{sheet_name or 'unknown'}')"
            ),
            error_code="invalid_value",
            function_name="_validate_entry_dates",
        )

    below = df.filter(below_min_mask).select(
        "file_name", "product", "product_entry_date", "product_table_year", "product_sheet_name"
    )
    for file_name, product, entry_date, table_year_val, sheet_name in below.iter_rows():
        error_collector.add_error(
            file_name=file_name or "unknown",
            patient_id=product or "unknown",
            column="product_entry_date",
            original_value=str(entry_date),
            error_message=(
                f"product_entry_date {entry_date} before "
                f"product_table_year {table_year_val} - {YEAR_FLOOR_DELTA} "
                f"(sheet '{sheet_name or 'unknown'}')"
            ),
            error_code="invalid_value",
            function_name="_validate_entry_dates",
        )

    return df.with_columns(
        pl.when(above_max_mask)
        .then(error_date)
        .otherwise(pl.col("product_entry_date"))
        .alias("product_entry_date")
    )


def _fill_product_names_and_sort(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.7 — forward-fill ``product`` then sort inside each product group.

    R runs this inside a per-sheet for-loop, so forward_fill and the
    first/last tier windows are scoped to (product, product_sheet_name).
    Without that scoping a null product at the top of sheet N would pick
    up the last product of sheet N-1, and a single product appearing in
    multiple sheets would collapse to one start/end pair instead of one
    per sheet.

    Within each (sheet, product) group the rank expression mirrors R's
    (read_product_data.R:610-615):
        rank = 1                       if first row in group
             = n + 2                   if last row in group
             = row_number              if middle row with null date (preserves input order)
             = dense_rank(date) + 1    if middle row with valid date
    Stable sort on (product_table_month, product, _rank) reproduces R's
    per-sheet for-loop + rbind output: sheet-major, product-minor.

    The parse-failure sentinel (``settings.error_val_date`` = 9999-09-09)
    counts as null for rank purposes — R drops unparseable dates to NA, so
    the input-order branch must catch sentinels too. Without this, sentinels
    sort to the dense_d+1 end-of-changes position and corrupt the
    cumulative-balance order vs. R.
    """
    if "product" not in df.columns:
        return df
    if "index" not in df.columns:
        raise KeyError(
            "_fill_product_names_and_sort requires an 'index' column; run _add_row_index first"
        )

    group = ["product_sheet_name", "product"] if "product_sheet_name" in df.columns else ["product"]
    sheet_group = ["product_sheet_name"] if "product_sheet_name" in df.columns else None

    if sheet_group is not None:
        df = df.with_columns(pl.col("product").forward_fill().over(sheet_group))
    else:
        df = df.with_columns(pl.col("product").forward_fill())

    row_n = pl.col("index").rank("ordinal").over(group).cast(pl.Int64)
    group_n = pl.col("index").count().over(group).cast(pl.Int64)
    has_date = "product_entry_date" in df.columns
    dense_d = (
        pl.col("product_entry_date").rank("dense").over(group).cast(pl.Int64)
        if has_date
        else pl.lit(None, dtype=pl.Int64)
    )
    date_is_null = (
        (
            pl.col("product_entry_date").is_null()
            | (pl.col("product_entry_date") == pl.lit(settings.error_val_date).str.to_date())
        )
        if has_date
        else pl.lit(True)
    )

    rank_expr = (
        pl.when(row_n == 1)
        .then(pl.lit(1, dtype=pl.Int64))
        .when(row_n == group_n)
        .then(group_n + 2)
        .when(date_is_null)
        .then(row_n)
        .otherwise(dense_d + 1)
        .alias("_rank")
    )

    sort_cols: list[str] = []
    if "product_table_month" in df.columns:
        sort_cols.append("product_table_month")
    sort_cols.extend(["product", "_rank"])

    return (
        df.with_columns(rank_expr)
        .sort(sort_cols, nulls_last=True, maintain_order=True)
        .drop("_rank")
    )


def _extract_balance_from_received(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.8 — move stray balance values out of ``product_units_released``.

    For trackers (e.g. 2019 PKH, 2020 STH) where "Balance" appears in
    ``product_units_received``, the value sitting in ``product_units_released``
    is relocated to ``product_received_from`` and released is cleared.

    R applies this rewrite inside its per-sheet loop (helper_product_data.R:329);
    Python's clean pipeline operates on the whole-file DataFrame, so we scope
    the trigger with .over("product_sheet_name") to avoid blanking
    ``product_received_from`` on clean sheets that share a file with a sheet
    using the "Balance" convention.

    Diverges from R (helper_product_data.R:329-335): R's case_when has no
    default arm, so unmatched rows on a triggered sheet have their
    ``product_received_from`` nulled. The trigger regex ``(?i)Balance``
    substring-matches "START BALANCE" / "END BALANCE" — present on every
    standard sheet — so R's no-default behaviour silently wipes legitimate
    supplier names (e.g. ``DKSH`` on Mahosot 2020 stock-receipt rows).
    Python preserves the value via the ``.otherwise`` arm so audit-trail
    data survives. Mutation of ``product_units_released`` is correspondingly
    scoped to actual Balance rows (not all triggered rows) so that
    preserving ``received_from`` on a non-Balance row does not collateral
    a non-null ``released`` on the same row.
    """
    required = (
        "product_units_received",
        "product_units_released",
        "product_received_from",
        "product_sheet_name",
    )
    if not all(c in df.columns for c in required):
        return df

    balance_mask = pl.col("product_units_received").cast(pl.Utf8).str.contains("(?i)Balance")
    sheet_triggered = (
        balance_mask.any().over("product_sheet_name")
        & pl.col("product_received_from").is_null().any().over("product_sheet_name")
    )

    if not df.select(sheet_triggered.any()).item():
        return df

    # Materialize the trigger predicates before mutating product_received_from.
    # `sheet_triggered` includes `received_from.is_null().any().over(sheet)`; if
    # we let it re-evaluate in the second .with_columns() below, sheets where
    # every row is a Balance marker (e.g. 2019 PKH Oct19) flip the trigger to
    # False after the first call populates received_from on every row, and the
    # released-clear pass becomes a no-op. Caching pins the pre-mutation truth.
    df = df.with_columns(
        sheet_triggered.alias("_sheet_triggered"),
        balance_mask.alias("_balance_mask"),
    )

    # Two positive arms relocate the balance value into received_from on
    # actual Balance-marker rows; the catch-all preserves received_from on
    # all other rows. R's case_when has no default and would null those
    # rows — see docstring. The "Total" arm before the catch-all nulls
    # typist subtotal labels (e.g. "Accu-Chek Performa | Total | 35"
    # subtotal rows in Penang DC / VNCH / Mandalay 2019 trackers); R nulled
    # these implicitly via its no-default, and "Total" is never a real
    # supplier — it's the label the typist put on the end-of-product-block
    # subtotal row.
    df = df.with_columns(
        pl.when(pl.col("_sheet_triggered") & pl.col("_balance_mask") & pl.col("product_units_released").is_not_null())
        .then(pl.col("product_units_released").cast(pl.Utf8))
        .when(pl.col("_sheet_triggered") & pl.col("_balance_mask") & pl.col("product_received_from").is_not_null())
        .then(pl.col("product_received_from").cast(pl.Utf8))
        .when(pl.col("product_received_from") == "Total")
        .then(pl.lit(None, dtype=pl.Utf8))
        .otherwise(pl.col("product_received_from"))
        .alias("product_received_from")
    )
    df = df.with_columns(
        pl.when(pl.col("_sheet_triggered") & pl.col("_balance_mask") & pl.col("product_received_from").is_not_null())
        .then(pl.lit(None, dtype=pl.Utf8))
        .otherwise(pl.col("product_units_released"))
        .alias("product_units_released")
    )
    return df.drop("_sheet_triggered", "_balance_mask")


def _recode_na_units_to_zero(df: pl.DataFrame) -> pl.DataFrame:
    """Steps 2.9 and 2.12 — fill NA in unit columns with 0.

    Applied twice: once before the string cleans in 2.10/2.11 and once after
    to catch nulls introduced by those cleans. Respects column dtype — Utf8
    cols get "0", numeric cols get 0.
    """
    for col in UNIT_COLS:
        if col not in df.columns:
            continue
        fill: float | str = 0 if df.schema[col].is_numeric() else "0"
        df = df.with_columns(pl.col(col).fill_null(fill))
    return df


def _clean_received_from(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.10 — normalise the ``product_received_from`` column.

    If ``product_units_received`` contains "START", the corresponding
    ``product_received_from`` value is copied to ``product_balance`` as the
    start balance. Purely numeric entries (should be supplier names) are
    removed.
    """
    if "product_received_from" not in df.columns:
        return df

    if "product_units_received" in df.columns:
        # Preserve existing product_balance on non-START rows. Earlier code
        # used .otherwise(pl.lit(None)) which only happened to be a no-op
        # because nothing populates product_balance before this step; if a
        # future step seeds it, that work would be silently wiped.
        # .over("product_sheet_name") matches R's per-sheet loop semantics
        # (helper_product_data.R:354-377) — defensive even though the current
        # row-wise when/then/otherwise has no cross-row dependency.
        if "product_balance" not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias("product_balance"))
        start_mask = pl.col("product_units_received").cast(pl.Utf8).str.contains("(?i)START")
        df = df.with_columns(
            pl.when(start_mask)
            .then(pl.col("product_received_from").cast(pl.Utf8))
            .otherwise(pl.col("product_balance").cast(pl.Utf8))
            .over("product_sheet_name")
            .alias("product_balance")
        )

    no_alpha = ~pl.col("product_received_from").cast(pl.Utf8).str.contains(r"[A-Za-z]")
    df = df.with_columns(
        pl.when(pl.col("product_received_from").is_not_null() & no_alpha)
        .then(pl.lit(None))
        .otherwise(pl.col("product_received_from"))
        .alias("product_received_from")
    )
    return df


def _clean_units_received(
    df: pl.DataFrame,
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """Step 2.11 — zero out balance markers and cast to numeric.

    Rows where ``product_units_received`` contains "START", "END" or
    "BALANCE" are set to 0. Remaining values are cast to numeric; failures
    yield null (then 0 via the second pass of step 2.12) and emit one
    ``type_conversion`` entry per row to ``error_collector`` — R-parity with
    ``script3_create_table_product_data.R::preparing_product_fields``'s
    ``invalid_value`` warnings.
    """
    if "product_units_received" not in df.columns:
        return df

    marker_mask = pl.col("product_units_received").cast(pl.Utf8).str.contains(
        "(?i)START|END|BALANCE"
    )
    casted = pl.col("product_units_received").cast(pl.Float64, strict=False)

    failure_mask = (
        pl.col("product_units_received").is_not_null() & ~marker_mask & casted.is_null()
    )
    failures = df.filter(failure_mask)
    for row in failures.iter_rows(named=True):
        original = row["product_units_received"]
        error_collector.add_error(
            file_name=row.get("file_name") or "unknown",
            patient_id=row.get("product") or "unknown",
            column="product_units_received",
            error_code="type_conversion",
            function_name="_clean_units_received",
            original_value=str(original),
            error_message=(
                f"product_units_received '{original}' could not be converted to numeric"
            ),
        )

    return df.with_columns(
        pl.when(marker_mask).then(pl.lit(0.0)).otherwise(casted).alias("product_units_received")
    )


def _remove_empty_data_rows(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.13 — drop rows with no meaningful transaction data.

    Removes rows where units_received, units_released, units_returned,
    released_to, entry_date and balance are all null.
    """
    existing = [c for c in EMPTY_ROW_COLS if c in df.columns]
    if not existing:
        return df
    all_null = pl.all_horizontal([pl.col(c).is_null() for c in existing])
    return df.filter(~all_null)


def _compute_balance_status(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.14 — label each row ``start`` / ``change`` / ``end`` per (product, sheet).

    First row in each (product, product_sheet_name) group is ``start``, last
    is ``end``, all others are ``change``. R processes this per-sheet, so a
    product that appears in 12 sheets has 12 start rows and 12 end rows —
    not a single start/end across the whole tracker.
    """
    if "index" not in df.columns:
        raise KeyError(
            "_compute_balance_status requires an 'index' column; run _add_row_index first"
        )

    group = ["product_sheet_name", "product"] if "product_sheet_name" in df.columns else ["product"]

    return df.with_columns(
        pl.when(pl.col("index") == pl.col("index").first().over(group))
        .then(pl.lit("start"))
        .when(pl.col("index") == pl.col("index").last().over(group))
        .then(pl.lit("end"))
        .otherwise(pl.lit("change"))
        .alias("product_balance_status")
    )


def _compute_running_balance(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.15 — compute the running stock balance per product.

    Formula: ``balance[i] = balance[i-1] - released[i] + received[i]``.
    For year >= 2021 the ``end`` rows' received/released are zeroed first
    (they are summary rows, not real transactions). The year is read from
    the ``product_table_year`` column (set by extraction).

    Implementation uses a vectorized cumsum per product instead of R's
    iterative loop. Equivalent when step 2.12 has filled unit-column nulls
    with 0 and step 2.7's sort is stable — corrupt upstream state could
    diverge (R's loop propagates NA forward; cumsum treats it as 0 after
    2.12's fill).

    Preconditions: ``_fill_product_names_and_sort`` (step 2.7) and
    ``_compute_balance_status`` (step 2.14) must have run. The first
    positional row in each (sheet, product) group must be labeled
    ``"start"`` because the cumsum below seeds from
    ``product_balance.first().over(group)``.
    """
    group = (
        ["product_sheet_name", "product"]
        if "product_sheet_name" in df.columns
        else ["product"]
    )

    if "product_balance_status" not in df.columns:
        raise RuntimeError(
            "_compute_running_balance requires product_balance_status; "
            "run _compute_balance_status (step 2.14) first"
        )
    if df.height > 0:
        first_status = df.select(
            pl.col("product_balance_status").first().over(group).alias("_fs")
        )["_fs"]
        if not (first_status == "start").all():
            bad_groups = (
                df.with_columns(
                    pl.col("product_balance_status").first().over(group).alias("_fs")
                )
                .filter(pl.col("_fs") != "start")
                .select(group)
                .unique()
                .height
            )
            raise RuntimeError(
                f"_compute_running_balance precondition violated: {bad_groups} "
                "(sheet, product) groups have a non-'start' row first. "
                "Did _fill_product_names_and_sort (step 2.7) run?"
            )

    casts = [
        pl.col("product_balance").cast(pl.Float64, strict=False),
        pl.col("product_units_released").cast(pl.Float64, strict=False),
    ]
    if "product_units_returned" in df.columns:
        casts.append(pl.col("product_units_returned").cast(pl.Float64, strict=False))
    df = df.with_columns(casts)

    if "product_table_year" in df.columns:
        year_gate = (
            pl.col("product_table_year").is_not_null()
            & (pl.col("product_table_year") >= 2021)
            & (pl.col("product_balance_status") == "end")
        )
        df = df.with_columns(
            pl.when(year_gate)
            .then(pl.lit(0.0))
            .otherwise(pl.col("product_units_received"))
            .alias("product_units_received"),
            pl.when(year_gate)
            .then(pl.lit(0.0))
            .otherwise(pl.col("product_units_released"))
            .alias("product_units_released"),
        )

    df = df.with_columns(
        pl.when(
            (pl.col("product_balance_status") == "start")
            & pl.col("product_balance").is_null()
        )
        .then(pl.col("product_units_received") - pl.col("product_units_released"))
        .otherwise(pl.col("product_balance"))
        .alias("product_balance")
    )

    is_start = pl.col("product_balance_status") == "start"
    delta = (
        pl.when(is_start)
        .then(pl.lit(0.0))
        .otherwise(pl.col("product_units_received") - pl.col("product_units_released"))
    )
    df = df.with_columns(
        (
            pl.col("product_balance").first().over(group)
            + delta.cum_sum().over(group)
        )
        .round(10)
        .alias("product_balance")
    )
    return df


def _validate_negative_balances(
    df: pl.DataFrame,
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """Step 2.18 — log rows with a negative ``product_balance``.

    Data is not modified; each negative-balance row is reported via the
    error collector for downstream investigation.
    """
    if "product_balance" not in df.columns:
        return df

    negatives = df.filter(
        pl.col("product_balance").is_not_null() & (pl.col("product_balance") < 0)
    ).select("file_name", "product_balance", "product", "product_sheet_name")
    for file_name, balance, product, sheet_name in negatives.iter_rows():
        error_collector.add_error(
            file_name=file_name or "unknown",
            patient_id="unknown",
            column="product_balance",
            original_value=balance,
            error_message=(
                f"Negative balance {balance} for product "
                f"'{product or 'unknown'}' in sheet "
                f"'{sheet_name or 'unknown'}'"
            ),
            error_code="invalid_value",
            function_name="_validate_negative_balances",
        )
    return df


def _report_unknown_products(
    df: pl.DataFrame,
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """Step 2.19 — flag product names missing from the Stock_Summary reference.

    Case-insensitive comparison against the known product list. DataFrame is
    returned unchanged; violations are logged to the error collector.
    """
    if "product" not in df.columns:
        return df

    known = set(load_known_products())

    # R logs unknowns per-sheet; replicate by keying errors on
    # (file_name, product_sheet_name, product) triples.
    cols = [
        c for c in ("file_name", "product_sheet_name", "product") if c in df.columns
    ]
    unknowns = (
        df.filter(pl.col("product").is_not_null())
        .with_columns(pl.col("product").str.to_lowercase().alias("_lower"))
        .filter(~pl.col("_lower").is_in(list(known)))
        .select(cols)
        .unique()
    )
    for row in unknowns.iter_rows(named=True):
        error_collector.add_error(
            file_name=row.get("file_name") or "unknown",
            patient_id="unknown",
            column="product",
            original_value=row["product"],
            error_message=(
                f"Unknown product '{row['product']}' in sheet "
                f"'{row.get('product_sheet_name') or 'unknown'}'"
            ),
            error_code="invalid_value",
            function_name="_report_unknown_products",
        )
    return df


def _add_product_categories(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.20 — left-join ``product_category`` from Stock_Summary.

    Products not present in the reference receive a null category.
    """
    if "product" not in df.columns:
        return df

    # columns: product (lowercased), product_category
    categories = load_product_categories()

    df = df.with_columns(
        pl.col("product").cast(pl.Utf8).str.to_lowercase().alias("_product_join")
    )
    df = df.join(
        categories.rename({"product": "_product_join"}),
        on="_product_join",
        how="left",
    )
    return df.drop("_product_join")


def _extract_unit_capacity(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.21 — parse units-per-package from the product name.

    Reads parenthesised hints such as ``(2s)`` or ``(10's)`` into
    ``product_unit_capacity``. ``singles`` maps to 1; absent hints default
    to 1 as well.
    """
    if "product" not in df.columns:
        return df.with_columns(
            pl.lit(1, dtype=pl.Int32).alias("product_unit_capacity")
        )

    paren = pl.col("product").cast(pl.Utf8).str.extract(r"\(([^()]+)\)", 1)
    paren_normalized = (
        pl.when(paren.str.contains("(?i)singles"))
        .then(pl.lit("1s"))
        .otherwise(paren)
    )
    # Digits immediately followed by an optional apostrophe and then "s"
    # (covers "(10s)", "(5's)"). Non-matching paren content → null → 1.
    digits = paren_normalized.str.extract(r"(\d+)'?s", 1)
    capacity = digits.cast(pl.Int32, strict=False).fill_null(1)

    return df.with_columns(capacity.alias("product_unit_capacity"))
