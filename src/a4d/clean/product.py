"""Product data cleaning pipeline.

Mirrors ``clean/patient.py`` architecture: a single orchestrator
(``clean_product_data``) dispatches to step-scoped private helpers.

The ``2.x`` step numbers below are this pipeline's own ordering vocabulary and
are referenced by the tests. They are not decorative: several steps are only
correct in position -- dates are parsed (2.6) before rows are sorted (2.7),
because the sort is chronological; the balance is accumulated (2.15) only after
that sort; and units are recoded to zero both before and after schema seeding
(2.9/2.12) because a column the schema adds arrives null.
"""

from pathlib import Path

import polars as pl

from a4d.clean.buddhist_era import (
    BUDDHIST_ERA_OFFSET,
    BUDDHIST_ERA_THRESHOLD,
    gregorian_from_buddhist,
)
from a4d.clean.converters import (
    normalize_excel_formula_errors,
    parse_date_column,
    safe_convert_column,
)
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
    """Clean raw product data through the full 2.x step sequence.

    Executes steps 2.1-2.22 in order and returns a DataFrame conforming to
    the product meta schema defined in ``clean/schema_product.py``.

    Args:
        df_raw: Raw product DataFrame from extraction.
        error_collector: Accumulator for row-level data quality errors.

    Returns:
        Cleaned product DataFrame.
    """
    if df_raw.width == 0:
        # No product section found in any sheet (e.g. pre-product-tracking
        # tracker years) -- extraction hands back a columnless DataFrame.
        # The step sequence below assumes at least a "product" column, so
        # short-circuit to an empty-but-schema-conformant result rather than
        # letting `apply_schema` synthesize a single all-null row from a
        # literal with nothing to broadcast against.
        return pl.DataFrame(schema=get_product_data_schema())

    # Null out (and log) the source trackers' own formula-error strings,
    # which extraction preserves verbatim (ticket 27). Runs before the step
    # sequence so no step sees a "#DIV/0!" where it expects a value.
    df_raw = normalize_excel_formula_errors(df_raw, error_collector, patient_id_col="product")

    df = _normalize_empty_strings_to_null(df_raw)  # 2.0 (see helper docstring)
    df = _split_multi_product_cells(df)  # 2.1
    df = _switch_misplaced_columns(df)  # 2.3
    df = _remove_uninformative_rows(df)  # 2.4
    df = _add_row_index(df)  # 2.5
    df = _format_dates(df, error_collector)  # 2.6
    _check_entry_dates_match_sheet(df, error_collector)  # 2.6a (log only)
    df = _validate_entry_dates(df, error_collector)  # 2.6b
    df = _fill_product_names_and_sort(df)  # 2.7
    df = _extract_balance_from_received(df)  # 2.8
    df = _recode_na_units_to_zero(df)  # 2.9
    df = _clean_received_from(df)  # 2.10
    df = _clean_units_received(df, error_collector)  # 2.11
    df = _recode_na_units_to_zero(df)  # 2.12
    df = _remove_empty_data_rows(df)  # 2.13
    df = _compute_balance_status(df)  # 2.14
    df = _compute_running_balance(df, error_collector)  # 2.15

    # 2.16 — type cast numeric/date columns via ErrorCollector; strip strings,
    # because end-whitespace never carries meaning here and an untrimmed value
    # fails allowed-value validation and lands on a sentinel.
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
    df = _report_unknown_products(df, error_collector)  # 2.19
    df = _add_product_categories(df)  # 2.20
    df = _extract_unit_capacity(df)  # 2.21
    # 2.22 cross-month combine happens at the table stage (S4-T1), not here.

    # Final schema conformance: guarantees 20 columns in schema order.
    df = apply_schema(df)
    # UNIT_COLS treat absence as 0 -- a stock movement that records no
    # quantity moved nothing -- so re-run the recode after schema seeding,
    # which fills any newly-added column with null.
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

    openpyxl returns an empty string for a blank Excel cell rather than None,
    so without this normalisation a row whose only content is that empty string
    survives `_remove_uninformative_rows` and `_remove_empty_data_rows` and
    reaches the output as a phantom stock movement (observed on 2024 CDA Dec24,
    which has one such row in product_units_received).
    """
    exprs = [
        pl.when(pl.col(c).str.strip_chars() == "").then(None).otherwise(pl.col(c)).alias(c)
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
    # "\d+" rather than "[1-9]+": the latter drops the leading digit of any
    # count containing a zero, turning "(10 box)" into 1. No tracker row in the
    # current corpus triggers box/unit extraction, so this is a correctness
    # guard rather than an observed fix.
    number_str = paren_text.str.extract(r"(\d+)", 1)

    df = df.with_columns(
        pl.when(has_paren_and_kw)
        .then(paren_text)
        .otherwise(pl.col("product_units_notes"))
        .alias("product_units_notes")
    )

    if "product_received_from" in df.columns:
        df = df.with_columns(
            pl.when(has_paren_and_kw & no_slash & pl.col("product_received_from").is_not_null())
            .then(number_str)
            .otherwise(pl.col("product_units_received"))
            .alias("product_units_received")
        )

    if "product_released_to" in df.columns:
        df = df.with_columns(
            pl.when(has_paren_and_kw & no_slash & pl.col("product_released_to").is_not_null())
            .then(number_str)
            .otherwise(pl.col("product_units_released"))
            .alias("product_units_released")
        )

    return df


def _switch_misplaced_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.3 — swap ``product_units_received`` with ``product_received_from``
    for each sheet that contains "Remaining Stock" in units_received.

    Observed in the 2018 PNG Nov/Dec trackers. The swap is scoped with
    .over(product_sheet_name) because this pipeline operates on the whole-file
    DataFrame: the defect is per-sheet, and an unscoped swap would corrupt the
    correctly-laid-out sheets in the same workbook.
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
    """Step 2.5 — add a 1-based ``index`` column recording input row order.

    Kept because several later steps sort the frame, and this is the only
    surviving record of the order the workbook actually listed rows in.
    """
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
    are junk: neither is a date the clinic recorded, and both would otherwise
    be published as though it had.
    """
    if "product_entry_date" not in df.columns:
        return df

    raw = pl.col("product_entry_date").cast(pl.Utf8).str.strip_chars()
    is_marker = raw.str.to_lowercase().is_in(list(PRODUCT_DATE_NA_MARKERS))
    as_num = raw.cast(pl.Float64, strict=False)
    is_tiny_serial = as_num.is_not_null() & (as_num > 0) & (as_num < MIN_PLAUSIBLE_EXCEL_SERIAL)

    return df.with_columns(
        pl.when(is_marker | is_tiny_serial)
        .then(pl.lit(None, dtype=pl.Utf8))
        .otherwise(pl.col("product_entry_date").cast(pl.Utf8))
        .alias("product_entry_date")
    )


def _format_dates(df: pl.DataFrame, error_collector: ErrorCollector) -> pl.DataFrame:
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
    return parse_date_column(df, "product_entry_date", error_collector, patient_id_col="product")


def _check_entry_dates_match_sheet(df: pl.DataFrame, error_collector: ErrorCollector) -> None:
    """Warn on entry dates that disagree with the sheet they were found on.

    One log entry per row where the parsed ``product_entry_date`` doesn't match
    ``(product_table_year, product_table_month)``. A movement filed on the
    March sheet but dated in July is either a typo or a misfiled row, and
    either way the workbook is what needs correcting -- so this reports rather
    than repairs. Sentinels, nulls, and Buddhist-era dates are skipped, since
    each is already accounted for elsewhere.

    Every parsed date is checked, not just numeric Excel serials, because
    ``parse_date_flexible`` accepts both serials and text and a mis-dated text
    cell is no less wrong than a mis-dated serial.

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
        "product_sheet_name"
        if "product_sheet_name" in df.columns
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


def _validate_entry_dates(df: pl.DataFrame, error_collector: ErrorCollector) -> pl.DataFrame:
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
      (1900-2014 in 2020+ trackers), but sentinelling them would drop the row
      out of chronological order and so distort the running balance that step
      2.15 accumulates. Preserving the date keeps the ledger trajectory intact
      while the audit log retains the data-quality flag.

    Above/below cases are logged with distinct messages so triage in
    ``table_error_messages.parquet`` can distinguish them.

    * **Implausible era** (year at or beyond ``BUDDHIST_ERA_THRESHOLD`` that is
      not this tracker's own Buddhist-era year): logged under
      ``implausible_era_date`` AND replaced with ``error_val_date``. Ticket 32
      found the earlier blanket ">= 2400 is exempt" rule published
      ``5567-08-19`` and ``3026-04-30`` — Excel serials 1,339,576 and 411,384 —
      straight into the product table, plus a Hat Yai ``2525`` in a tracker
      whose BE year is 2568.
    * **Buddhist era** (year inside this tracker's own BE band): shifted back
      543 years and logged under ``buddhist_era_converted`` (ticket 61). A BE
      date is the calendar a Thai clinic uses, not an error it made, so the
      pipeline publishes one calendar downstream rather than a stock movement
      dated 543 years in the future -- 22 product rows. A BE leap day that has
      no Gregorian counterpart
      (2568-02-29 -> 2025-02-29) yields null from the shift and falls through
      to the implausible-era branch rather than being invented.

    The parse-failure sentinel (9999-09-09) is exempt from all branches so it is
    not re-clobbered or double-logged.
    """
    if "product_entry_date" not in df.columns or "product_table_year" not in df.columns:
        return df

    error_date = pl.lit(settings.error_val_date).str.to_date()
    table_year = pl.col("product_table_year").cast(pl.Int32)
    max_valid = pl.date(table_year, 12, 31)
    min_valid = pl.date(table_year - YEAR_FLOOR_DELTA, 1, 1)

    entry_year = pl.col("product_entry_date").dt.year()
    # A year at or beyond the threshold is only credible as this tracker's own
    # Buddhist-era year, so the exemption mirrors the Gregorian window rather
    # than admitting everything above 2400 (ticket 32).
    in_buddhist_band = (entry_year >= table_year + BUDDHIST_ERA_OFFSET - YEAR_FLOOR_DELTA) & (
        entry_year <= table_year + BUDDHIST_ERA_OFFSET
    )
    is_sentinel = pl.col("product_entry_date") == error_date
    converted = gregorian_from_buddhist("product_entry_date")
    convert_mask = (
        pl.col("product_entry_date").is_not_null()
        & (entry_year >= BUDDHIST_ERA_THRESHOLD)
        & in_buddhist_band
        & ~is_sentinel
        & converted.is_not_null()
    )
    implausible_era_mask = (
        pl.col("product_entry_date").is_not_null()
        & (entry_year >= BUDDHIST_ERA_THRESHOLD)
        & ~convert_mask
        & ~is_sentinel
    )

    convertible = df.filter(convert_mask).select(
        "file_name", "product", "product_entry_date", "product_table_year", "product_sheet_name"
    )
    for file_name, product, entry_date, table_year_val, sheet_name in convertible.iter_rows():
        error_collector.add_error(
            file_name=file_name or "unknown",
            patient_id=product or "unknown",
            column="product_entry_date",
            original_value=str(entry_date),
            error_message=(
                f"product_entry_date {entry_date} is the Buddhist-era year of "
                f"product_table_year {table_year_val}; converted to "
                f"{entry_date.year - BUDDHIST_ERA_OFFSET}-{entry_date.month:02d}-"
                f"{entry_date.day:02d} (sheet '{sheet_name or 'unknown'}')"
            ),
            error_code="buddhist_era_converted",
            function_name="_validate_entry_dates",
        )

    implausible = df.filter(implausible_era_mask).select(
        "file_name", "product", "product_entry_date", "product_table_year", "product_sheet_name"
    )
    for file_name, product, entry_date, table_year_val, sheet_name in implausible.iter_rows():
        error_collector.add_error(
            file_name=file_name or "unknown",
            patient_id=product or "unknown",
            column="product_entry_date",
            original_value=str(entry_date),
            error_message=(
                f"product_entry_date {entry_date} is neither a Gregorian date nor "
                f"the Buddhist-era year of product_table_year {table_year_val} "
                f"(sheet '{sheet_name or 'unknown'}')"
            ),
            error_code="implausible_era_date",
            function_name="_validate_entry_dates",
        )

    not_buddhist = entry_year < BUDDHIST_ERA_THRESHOLD
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
        pl.when(above_max_mask | implausible_era_mask)
        .then(error_date)
        .when(convert_mask)
        .then(converted)
        .otherwise(pl.col("product_entry_date"))
        .alias("product_entry_date")
    )


def _fill_product_names_and_sort(df: pl.DataFrame) -> pl.DataFrame:
    """Step 2.7 — forward-fill ``product`` then sort inside each product group.

    Forward-fill and the first/last tier windows are scoped to
    (product, product_sheet_name). Without that scoping a null product at the
    top of sheet N picks up the last product of sheet N-1, and a single product
    appearing in several sheets collapses to one start/end pair instead of one
    per sheet.

    Within each (sheet, product) group the rank expression is:
        rank = 1                       if first row in group
             = n + 2                   if last row in group
             = row_number              if middle row with null date (preserves input order)
             = dense_rank(date) + 1    if middle row with valid date
    Stable sort on (product_table_month, product, _rank) gives sheet-major,
    product-minor order, which is how the ledger reads in the workbook.

    The parse-failure sentinel (``settings.error_val_date`` = 9999-09-09)
    counts as null for rank purposes: a row whose date could not be read has
    no place in a chronological ordering, so it holds its input position.
    Without this it sorts to the dense_rank+1 end-of-changes slot and the
    running balance accumulates in the wrong order.
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

    The trigger is scoped with .over("product_sheet_name") because this
    pipeline operates on the whole-file DataFrame and the convention is
    per-sheet: an unscoped trigger blanks ``product_received_from`` on the
    clean sheets sharing the workbook.

    Rows on a triggered sheet that are *not* Balance rows keep their
    ``product_received_from`` via the ``.otherwise`` arm. This matters because
    the trigger regex ``(?i)Balance`` substring-matches "START BALANCE" and
    "END BALANCE", which appear on every standard sheet -- so a rule without a
    default arm silently wipes legitimate supplier names (``DKSH`` on the
    Mahosot 2020 stock-receipt rows). Mutation of ``product_units_released`` is
    correspondingly scoped to actual Balance rows, so preserving
    ``received_from`` on a non-Balance row does not leave a stray
    ``released`` value beside it.
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
    sheet_triggered = balance_mask.any().over("product_sheet_name") & pl.col(
        "product_received_from"
    ).is_null().any().over("product_sheet_name")

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
    # all other rows -- see docstring for why the catch-all is required.
    # The "Total" arm before the catch-all nulls
    # typist subtotal labels (e.g. "Accu-Chek Performa | Total | 35"
    # subtotal rows in Penang DC / VNCH / Mandalay 2019 trackers). "Total" is
    # never a real supplier -- it is the label the typist put on the
    # end-of-product-block subtotal row.
    df = df.with_columns(
        pl.when(
            pl.col("_sheet_triggered")
            & pl.col("_balance_mask")
            & pl.col("product_units_released").is_not_null()
        )
        .then(pl.col("product_units_released").cast(pl.Utf8))
        .when(
            pl.col("_sheet_triggered")
            & pl.col("_balance_mask")
            & pl.col("product_received_from").is_not_null()
        )
        .then(pl.col("product_received_from").cast(pl.Utf8))
        .when(pl.col("product_received_from") == "Total")
        .then(pl.lit(None, dtype=pl.Utf8))
        .otherwise(pl.col("product_received_from"))
        .alias("product_received_from")
    )
    df = df.with_columns(
        pl.when(
            pl.col("_sheet_triggered")
            & pl.col("_balance_mask")
            & pl.col("product_received_from").is_not_null()
        )
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
        # .over("product_sheet_name") scopes this per sheet, matching how the
        # convention is applied in the workbooks -- defensive here, since the
        # row-wise when/then/otherwise has no cross-row dependency today.
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
    ``type_conversion`` entry per row to ``error_collector``, so a quantity
    that could not be read is recoverable from the log rather than silently
    becoming a zero movement.
    """
    if "product_units_received" not in df.columns:
        return df

    marker_mask = (
        pl.col("product_units_received").cast(pl.Utf8).str.contains("(?i)START|END|BALANCE")
    )
    casted = pl.col("product_units_received").cast(pl.Float64, strict=False)

    failure_mask = pl.col("product_units_received").is_not_null() & ~marker_mask & casted.is_null()
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
    is ``end``, all others are ``change``. The grouping is per-sheet, so a
    product appearing in 12 sheets has 12 start rows and 12 end rows rather
    than a single pair spanning the tracker -- each month's sheet opens and
    closes its own ledger, and the closing balance of one is what the next
    opens with.
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


def _compute_running_balance(
    df: pl.DataFrame, error_collector: ErrorCollector | None = None
) -> pl.DataFrame:
    """Step 2.15 — compute the running stock balance per product.

    Formula: ``balance[i] = balance[i-1] - released[i] + received[i]``.
    For year >= 2021 the ``end`` rows' received/released are zeroed first
    (they are summary rows, not real transactions). The year is read from
    the ``product_table_year`` column (set by extraction).

    Implemented as a vectorized cumsum per product. This is only correct
    because step 2.12 has already filled unit-column nulls with 0 and step
    2.7's sort is stable: cumsum treats a null as 0, so an unfilled null would
    silently contribute nothing instead of breaking the ledger visibly.

    Preconditions: ``_fill_product_names_and_sort`` (step 2.7) and
    ``_compute_balance_status`` (step 2.14) must have run. The first
    positional row in each (sheet, product) group must be labeled
    ``"start"`` because the cumsum below seeds from
    ``product_balance.first().over(group)``.

    Recomputing overwrites whatever balance the tracker recorded on
    ``change``/``end`` rows. Because step 2.7 sorts chronologically while the
    source's own balance column accumulates in data-entry order, the
    *intermediate* balances legitimately differ from the tracker's (31% of
    recorded rows on the real 248-tracker set) and are not worth reporting.
    The *closing* balance is order-independent, though, so a disagreement
    there means the transactions and the tracker's own recorded total do not
    add up -- a real source problem, and the only thing this step reports
    (ticket 36; 1.1% of groups on the same data).
    """
    group = ["product_sheet_name", "product"] if "product_sheet_name" in df.columns else ["product"]

    if "product_balance_status" not in df.columns:
        raise RuntimeError(
            "_compute_running_balance requires product_balance_status; "
            "run _compute_balance_status (step 2.14) first"
        )
    if df.height > 0:
        first_status = df.select(pl.col("product_balance_status").first().over(group).alias("_fs"))[
            "_fs"
        ]
        if not (first_status == "start").all():
            bad_groups = (
                df.with_columns(pl.col("product_balance_status").first().over(group).alias("_fs"))
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
        pl.when((pl.col("product_balance_status") == "start") & pl.col("product_balance").is_null())
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
    source_balance = df.select(
        pl.col("product_balance").alias("_source_balance"),
        *[pl.col(c) for c in group],
        pl.col("product_balance_status"),
        *([pl.col("index")] if "index" in df.columns else []),
        *([pl.col("file_name")] if "file_name" in df.columns else []),
    )

    df = df.with_columns(
        (pl.col("product_balance").first().over(group) + delta.cum_sum().over(group))
        .round(10)
        .alias("product_balance")
    )

    if error_collector is not None:
        _report_balance_reconciliation(df, source_balance, group, error_collector)
    return df


BALANCE_RECONCILIATION_ABS_TOL = 1e-6
BALANCE_RECONCILIATION_REL_TOL = 1e-9


def _report_balance_reconciliation(
    df: pl.DataFrame,
    source_balance: pl.DataFrame,
    group: list[str],
    error_collector: ErrorCollector,
) -> None:
    """Flag groups whose recomputed closing stock contradicts the tracker's own.

    Compares the last balance the source recorded on a ``change``/``end`` row
    (in the file's original input order, so the chronological re-sort cannot
    change which value counts as "the tracker's closing figure") against the
    computed closing balance. Groups where the source left every non-start
    balance blank -- the common case -- have nothing to reconcile and are
    skipped, since warning on them would bury the real signal.
    """
    recorded = source_balance.filter(
        (pl.col("product_balance_status") != "start") & pl.col("_source_balance").is_not_null()
    )
    if recorded.height == 0:
        return
    if "index" in recorded.columns:
        recorded = recorded.sort("index")
    source_closing = recorded.group_by(group).agg(
        pl.col("_source_balance").last().alias("_source_closing")
    )

    computed_closing = df.group_by(group).agg(
        pl.col("product_balance").last().alias("_computed_closing"),
        *([pl.col("file_name").last().alias("_file_name")] if "file_name" in df.columns else []),
    )

    joined = source_closing.join(computed_closing, on=group, how="inner")
    for row in joined.iter_rows(named=True):
        source_value = row["_source_closing"]
        computed = row["_computed_closing"]
        if computed is None:
            continue
        tolerance = max(
            BALANCE_RECONCILIATION_ABS_TOL,
            BALANCE_RECONCILIATION_REL_TOL * max(abs(source_value), abs(computed)),
        )
        if abs(source_value - computed) <= tolerance:
            continue
        product = row.get("product") or "unknown"
        sheet_name = row.get("product_sheet_name") or "unknown"
        error_collector.add_error(
            file_name=row.get("_file_name") or "unknown",
            patient_id="unknown",
            column="product_balance",
            original_value=source_value,
            error_message=(
                f"Closing balance mismatch for product '{product}' in sheet "
                f"'{sheet_name}': tracker recorded {source_value}, but the "
                f"recorded transactions add up to {computed} "
                f"(difference {round(computed - source_value, 10)}). "
                "The stock movements and the tracker's own total do not agree."
            ),
            error_code="balance_reconciliation",
            function_name="_compute_running_balance",
        )


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

    # Key errors on (file_name, product_sheet_name, product) triples, so an
    # unknown product is reported once per sheet it appears on rather than
    # once per row -- the correction is to the reference list or the sheet's
    # spelling, and both are per-sheet facts.
    cols = [c for c in ("file_name", "product_sheet_name", "product") if c in df.columns]
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

    df = df.with_columns(pl.col("product").cast(pl.Utf8).str.to_lowercase().alias("_product_join"))
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
        return df.with_columns(pl.lit(1, dtype=pl.Int32).alias("product_unit_capacity"))

    paren = pl.col("product").cast(pl.Utf8).str.extract(r"\(([^()]+)\)", 1)
    paren_normalized = (
        pl.when(paren.str.contains("(?i)singles")).then(pl.lit("1s")).otherwise(paren)
    )
    # Digits immediately followed by an optional apostrophe and then "s"
    # (covers "(10s)", "(5's)"). Non-matching paren content → null → 1.
    digits = paren_normalized.str.extract(r"(\d+)'?s", 1)
    capacity = digits.cast(pl.Int32, strict=False).fill_null(1)

    return df.with_columns(capacity.alias("product_unit_capacity"))
