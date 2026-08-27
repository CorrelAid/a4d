"""Type conversion utilities with error tracking.

This module provides vectorized type conversion functions that track failures
in an ErrorCollector, without ever raising: a bad cell is a data-quality
finding to report, not a reason to abandon a tracker.

The pattern is:
1. Try vectorized conversion (fast, handles 95%+ of data)
2. Detect failures (nulls after conversion but not before)
3. Log only failed rows to ErrorCollector
4. Replace failures with error value
"""

from datetime import date

import polars as pl

from a4d.clean.date_parser import (
    MISSING_VALUE_MARKERS,
    TextDateRecovery,
    parse_date_detailed,
    rescue_date_typos,
)
from a4d.config import settings
from a4d.extract.common import EXCEL_ERROR_STRINGS
from a4d.findings import PLACE_COLUMNS, ErrorCode, report_finding, sheet_context


def normalize_excel_formula_errors(
    df: pl.DataFrame,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Null out Excel formula-error strings, logging each one (ticket 27).

    A tracker's own spreadsheet formula writes a literal error string
    (``#NUM!``, ``#DIV/0!``, ...) into a cell whenever an input it depends on
    is missing -- e.g. age-at-diagnosis when no diagnosis date was recorded,
    or BMI when height is blank. Extraction deliberately preserves that text
    so the raw layer stays a faithful capture of the source file; this is
    where it becomes ``null``.

    ``null``, not ``settings.error_val_numeric`` (999999): the sentinel means
    "a value was recorded but is invalid" (a garbled reading that failed to
    parse). Here no value could be computed at all, because a required input
    was never entered -- semantically absent, not invalid. Running before
    type conversion keeps these out of ``safe_convert_column``'s
    parse-failure branch, which would otherwise assign that wrong sentinel.

    Each nulled cell is logged under ``source_formula_error`` so the
    distinction between "source formula could not compute this" and "field
    was simply blank" survives into the error log, even though both end up
    ``null`` in the data.
    """
    data_cols = [col for col in df.columns if df.schema[col] == pl.String]
    if not data_cols:
        return df

    error_mask = pl.any_horizontal([pl.col(col).is_in(EXCEL_ERROR_STRINGS) for col in data_cols])
    if not df.select(error_mask.any()).item():
        return df

    for col in data_cols:
        offenders = df.filter(pl.col(col).is_in(EXCEL_ERROR_STRINGS))
        if offenders.is_empty():
            continue
        for row in offenders.iter_rows(named=True):
            report_finding(
                file_name=row.get(file_name_col) or None,
                patient_id=row.get(patient_id_col) or "unknown",
                column=col,
                original_value=row[col],
                message=(
                    f"Source tracker formula error '{row[col]}' in {col}: "
                    "a required input was not recorded, so no value could be computed"
                ),
                error_code="source_formula_error",
                **sheet_context(row),
                function_name="normalize_excel_formula_errors",
            )

    return df.with_columns(
        [
            pl.when(pl.col(col).is_in(EXCEL_ERROR_STRINGS))
            .then(None)
            .otherwise(pl.col(col))
            .alias(col)
            for col in data_cols
        ]
    )


def safe_convert_column(
    df: pl.DataFrame,
    column: str,
    target_type: type[pl.DataType] | pl.DataType,
    error_value: float | str | None = None,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Convert column to target type with vectorized error tracking.

    This function attempts vectorized type conversion and tracks any failures
    in the ErrorCollector. Vectorized: the slow per-row path runs only over
    the cells that actually failed.

    Args:
        df: Input DataFrame
        column: Column name to convert
        target_type: Target Polars data type (pl.Int32, pl.Float64, etc.)
        error_value: Value to use for failed conversions (default from settings)
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with converted column (failures replaced with error_value)

    Example:
        >>> collector = ErrorCollector()
        >>> df = safe_convert_column(
        ...     df=df,
        ...     column="age",
        ...     target_type=pl.Int32,
        ...,
        ... )
        >>> # Failures are logged in collector, replaced with ERROR_VAL_NUMERIC
    """
    # Determine error value based on target type if not provided
    if error_value is None:
        if target_type in (pl.Int32, pl.Int64, pl.Float32, pl.Float64):
            error_value = settings.error_val_numeric
        elif target_type in (pl.Utf8, pl.Categorical, pl.String):
            error_value = settings.error_val_character
        elif target_type == pl.Date:
            error_value = settings.error_val_date
        elif target_type == pl.Boolean:
            error_value = False  # Default for boolean conversion failures
        else:
            raise ValueError(f"Cannot determine error value for type {target_type}")

    # Skip if column doesn't exist
    if column not in df.columns:
        return df

    # Normalize empty/whitespace/missing-value strings to null BEFORE conversion
    # This ensures missing data stays null rather than becoming error values
    # A cell reading 'Nil' or '-' recorded an absence, not an unusable value,
    # so it must not pick up the 999999 'recorded but invalid' sentinel.
    if df[column].dtype in (pl.Utf8, pl.String):
        # Shared with the date path (MISSING_VALUE_MARKERS, clean/date_parser.py)
        # so the two cannot drift apart again -- they had, and a date cell
        # holding "-" reached the error sentinel where the numeric one nulled.
        df = df.with_columns(
            pl.when(
                pl.col(column)
                .str.strip_chars()
                .str.to_lowercase()
                .is_in(list(MISSING_VALUE_MARKERS))
                | (pl.col(column).str.strip_chars().str.len_chars() == 0)
            )
            .then(None)
            .otherwise(pl.col(column))
            .alias(column)
        )

    # Store original values for error reporting
    df = df.with_columns(pl.col(column).alias(f"_orig_{column}"))

    # Try vectorized conversion (strict=False allows nulls for failures)
    df = df.with_columns(pl.col(column).cast(target_type, strict=False).alias(f"_conv_{column}"))

    # Detect failures: became null but wasn't null before
    failed_mask = pl.col(f"_conv_{column}").is_null() & pl.col(f"_orig_{column}").is_not_null()

    # Extract failed rows for error logging
    failed_rows = df.filter(failed_mask)

    # Log each failure
    if len(failed_rows) > 0:
        for row in failed_rows.iter_rows(named=True):
            report_finding(
                file_name=row.get(file_name_col) or None,
                patient_id=row.get(patient_id_col) or "unknown",
                column=column,
                original_value=row[f"_orig_{column}"],
                message=f"Could not convert '{row[f'_orig_{column}']}' to {target_type}",
                error_code="type_conversion",
                **sheet_context(row),
                function_name="safe_convert_column",
            )

    # Replace failures with error value (cast to target type)
    df = df.with_columns(
        pl.when(failed_mask)
        .then(pl.lit(error_value).cast(target_type))
        .otherwise(pl.col(f"_conv_{column}"))
        .alias(column)
    )

    # Clean up temporary columns
    df = df.drop([f"_orig_{column}", f"_conv_{column}"])

    return df


def _apply_typo_rescue(
    df: pl.DataFrame,
    column: str,
    file_name_col: str,
    patient_id_col: str,
) -> pl.DataFrame:
    """Rewrite known month-name typos in-place before parsing.

    Builds a rescue_map from unique strings, logs each affected row to
    report_finding with code "typo_rescued", then applies the
    substitutions column-wide. No-op if no typos match.
    """
    rescue_map: dict[str, str] = {}
    for s in df[column].drop_nulls().unique().to_list():
        rescued, was_rescued = rescue_date_typos(s)
        if was_rescued:
            rescue_map[s] = rescued

    if not rescue_map:
        return df

    select_cols = [c for c in (file_name_col, patient_id_col, *PLACE_COLUMNS) if c in df.columns]
    for original, rescued_val in rescue_map.items():
        if select_cols:
            affected = df.filter(pl.col(column) == original).select(select_cols)
            for row in affected.iter_rows(named=True):
                file_name = row.get(file_name_col) or None
                patient_id = row.get(patient_id_col) or "unknown"
                report_finding(
                    file_name=file_name,
                    patient_id=str(patient_id),
                    column=column,
                    original_value=original,
                    message=f"date typo rescued: '{original}' -> '{rescued_val}'",
                    error_code="typo_rescued",
                    **sheet_context(row),
                    function_name="parse_date_column",
                )

    repl_expr = pl.col(column)
    for original, rescued_val in rescue_map.items():
        repl_expr = (
            pl.when(pl.col(column) == original).then(pl.lit(rescued_val)).otherwise(repl_expr)
        )
    return df.with_columns(repl_expr.alias(column))


def _log_text_recoveries(
    df: pl.DataFrame,
    column: str,
    detailed: dict[tuple[str, int | None], tuple[date | None, TextDateRecovery | None]],
    file_name_col: str,
    patient_id_col: str,
) -> None:
    """Record what the free-text recogniser decided, one code per decision.

    Three codes rather than one (ticket 39): "we read what was written", "we
    chose among several dates the cell named", and "we supplied a year the cell
    did not state" carry different amounts of confidence, and only the middle
    one is a source-tracker defect worth reporting back to a clinic.
    """
    reported = {
        pair: recovery
        for pair, (_, recovery) in detailed.items()
        if recovery is not None and recovery.value is not None
    }
    if not reported:
        return

    select_cols = [c for c in (file_name_col, patient_id_col, *PLACE_COLUMNS) if c in df.columns]
    for (text, tracker_year), recovery in reported.items():
        messages: list[tuple[str, ErrorCode]] = [
            (
                f"date read out of free text: {text!r} -> {recovery.value}",
                "date_recovered_from_text",
            )
        ]
        if recovery.tokens_found > 1:
            messages.append(
                (
                    f"cell names {recovery.tokens_found} dates, first used: "
                    f"{text!r} -> {recovery.value}",
                    "date_multiple_in_cell",
                )
            )
        if recovery.year_inferred:
            messages.append(
                (
                    f"no year in cell, tracker year {tracker_year} used: "
                    f"{text!r} -> {recovery.value}",
                    "date_year_inferred",
                )
            )

        affected = df.filter(pl.col(column).cast(pl.Utf8) == text)
        if select_cols:
            affected = affected.select(select_cols)
        for row in affected.iter_rows(named=True):
            file_name = row.get(file_name_col) or None
            patient_id = row.get(patient_id_col) or "unknown"
            for message, code in messages:
                report_finding(
                    file_name=file_name,
                    patient_id=str(patient_id),
                    column=column,
                    original_value=text,
                    message=message,
                    error_code=code,
                    **sheet_context(row),
                    function_name="parse_date_column",
                )


def parse_date_column(
    df: pl.DataFrame,
    column: str,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Parse date column using flexible date parser.

    Uses parse_date_flexible() to handle various date formats including:
    - Standard formats (ISO, DD/MM/YYYY, etc.)
    - Abbreviated month-year (Mar-18, Jan-20)
    - Excel serial numbers
    - 4-letter month names

    Args:
        df: Input DataFrame
        column: Column name to parse
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with parsed date column

    Example:
        >>> df = parse_date_column(
        ...     df=df,
        ...     column="hba1c_updated_date",
        ...,
        ... )
    """
    if column not in df.columns:
        return df

    # Substitute known month-name typos (e.g. "MACH" -> "MAR") before parsing,
    # logging each affected row so the source tracker remains visible to
    # data-quality triage. Skipped silently when no typos match.
    df = _apply_typo_rescue(df, column, file_name_col, patient_id_col)

    # Store original values for error reporting
    df = df.with_columns(pl.col(column).alias(f"_orig_{column}"))

    # Parse each distinct string once, then map back. Tracker data has heavy
    # duplication in date columns (e.g. "1/1/2024" repeating per row), so
    # dedup-then-map is much faster than a per-row Python call.
    # All-null columns short-circuit: map_elements can't infer Date dtype on
    # an empty-after-drop_nulls Series.
    # A note with no year in it is resolved against the tracker's own year
    # (ticket 39), so the same string can mean different dates in two files --
    # 2020 VNCH and 2021 VNCH both carry "26 Jun (ceton urine high)" for the
    # same patient. The dedup key therefore has to be the pair, not the string.
    col_str = df[column].cast(pl.Utf8)
    if "tracker_year" in df.columns:
        year_str = df["tracker_year"].cast(pl.Int32, strict=False)
    else:
        year_str = pl.Series("tracker_year", [None] * df.height, dtype=pl.Int32)
    pairs = [(s, y) for s, y in zip(col_str, year_str, strict=True) if s is not None]
    unique_strs = list(dict.fromkeys(pairs))
    if unique_strs:
        detailed = {
            pair: parse_date_detailed(pair[0], settings.error_val_date, pair[1])
            for pair in unique_strs
        }
        lookup = {pair: value for pair, (value, _) in detailed.items()}
        _log_text_recoveries(df, column, detailed, file_name_col, patient_id_col)
        parsed_series = pl.Series(
            f"_parsed_{column}",
            [
                lookup.get((s, y)) if s is not None else None
                for s, y in zip(col_str, year_str, strict=True)
            ],
            dtype=pl.Date,
        )
    else:
        parsed_series = pl.Series(f"_parsed_{column}", [None] * df.height, dtype=pl.Date)
    df = df.with_columns(parsed_series)

    # Detect failures: parsed to error date
    error_date = pl.lit(settings.error_val_date).str.to_date()
    failed_mask = (
        pl.col(f"_parsed_{column}").is_not_null()
        & (pl.col(f"_parsed_{column}") == error_date)
        & pl.col(f"_orig_{column}").is_not_null()
    )

    # Extract failed rows for error logging
    failed_rows = df.filter(failed_mask)

    # Log each failure
    if len(failed_rows) > 0:
        for row in failed_rows.iter_rows(named=True):
            report_finding(
                file_name=row.get(file_name_col) or None,
                patient_id=row.get(patient_id_col) or "unknown",
                column=column,
                original_value=row[f"_orig_{column}"],
                message=f"Could not parse date '{row[f'_orig_{column}']}'",
                error_code="type_conversion",
                **sheet_context(row),
                function_name="parse_date_column",
            )

    # Use parsed values
    df = df.with_columns(pl.col(f"_parsed_{column}").alias(column))

    # Clean up temporary columns
    df = df.drop([f"_orig_{column}", f"_parsed_{column}"])

    return df


def correct_decimal_sign(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Replace comma decimal separator with dot.

    Some trackers use European decimal format (1,5 instead of 1.5).

    Args:
        df: Input DataFrame
        column: Column name to correct

    Returns:
        DataFrame with corrected decimal signs

    Example:
        >>> df = correct_decimal_sign(df, "weight")
    """
    if column not in df.columns:
        return df

    df = df.with_columns(pl.col(column).cast(pl.Utf8).str.replace(",", ".").alias(column))

    return df


def cut_numeric_value(
    df: pl.DataFrame,
    column: str,
    min_val: float,
    max_val: float,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Replace out-of-range numeric values with error value.

    Args:
        df: Input DataFrame
        column: Column name to check
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with out-of-range values replaced

    Example:
        >>> df = cut_numeric_value(
        ...     df=df,
        ...     column="age",
        ...     min_val=0,
        ...     max_val=25,
        ...,
        ... )
    """
    if column not in df.columns:
        return df

    # Find values outside allowed range (excluding nulls and existing error values)
    invalid_mask = (
        pl.col(column).is_not_null()
        & (pl.col(column) != settings.error_val_numeric)
        & ((pl.col(column) < min_val) | (pl.col(column) > max_val))
    )

    # Extract invalid rows for error logging
    invalid_rows = df.filter(invalid_mask)

    # Log each invalid value
    if len(invalid_rows) > 0:
        for row in invalid_rows.iter_rows(named=True):
            report_finding(
                file_name=row.get(file_name_col) or None,
                patient_id=row.get(patient_id_col) or "unknown",
                column=column,
                original_value=row[column],
                message=f"Value {row[column]} outside allowed range [{min_val}, {max_val}]",
                error_code="value_out_of_range",
                **sheet_context(row),
                function_name="cut_numeric_value",
            )

    # Replace invalid values with error value
    df = df.with_columns(
        pl.when(invalid_mask)
        .then(pl.lit(settings.error_val_numeric))
        .otherwise(pl.col(column))
        .alias(column)
    )

    return df


def safe_convert_multiple_columns(
    df: pl.DataFrame,
    columns: list[str],
    target_type: type[pl.DataType] | pl.DataType,
    error_value: float | str | None = None,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Convert multiple columns to the same target type.

    Convenience function for batch conversion of columns.

    Args:
        df: Input DataFrame
        columns: List of column names to convert
        target_type: Target Polars data type
        error_value: Value to use for failed conversions
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with all specified columns converted

    Example:
        >>> df = safe_convert_multiple_columns(
        ...     df=df,
        ...     columns=["age", "height", "weight"],
        ...     target_type=pl.Float64,
        ...,
        ... )
    """
    for column in columns:
        df = safe_convert_column(
            df=df,
            column=column,
            target_type=target_type,
            error_value=error_value,
            file_name_col=file_name_col,
            patient_id_col=patient_id_col,
        )

    return df
