"""Type conversion utilities with error tracking.

This module provides vectorized type conversion functions that track failures
in an ErrorCollector. This replaces R's rowwise() conversion approach with
much faster vectorized operations.

The pattern is:
1. Try vectorized conversion (fast, handles 95%+ of data)
2. Detect failures (nulls after conversion but not before)
3. Log only failed rows to ErrorCollector
4. Replace failures with error value
"""

import polars as pl

from a4d.clean.date_parser import parse_date_flexible
from a4d.config import settings
from a4d.errors import ErrorCollector


def safe_convert_column(
    df: pl.DataFrame,
    column: str,
    target_type: type[pl.DataType] | pl.DataType,
    error_collector: ErrorCollector,
    error_value: float | str | None = None,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Convert column to target type with vectorized error tracking.

    This function attempts vectorized type conversion and tracks any failures
    in the ErrorCollector. Much faster than R's rowwise() approach.

    Args:
        df: Input DataFrame
        column: Column name to convert
        target_type: Target Polars data type (pl.Int32, pl.Float64, etc.)
        error_collector: ErrorCollector instance to track failures
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
        ...     error_collector=collector,
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
    # Matches R behavior where these values → NA (not conversion error)
    if df[column].dtype in (pl.Utf8, pl.String):
        # Common missing value representations to treat as null
        missing_values = ["", "N/A", "NA", "n/a", "na", "-", ".", "None", "none", "NULL", "null"]
        df = df.with_columns(
            pl.when(
                pl.col(column).str.strip_chars().is_in(missing_values)
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
            error_collector.add_error(
                file_name=row.get(file_name_col) or "unknown",
                patient_id=row.get(patient_id_col) or "unknown",
                column=column,
                original_value=row[f"_orig_{column}"],
                error_message=f"Could not convert to {target_type}",
                error_code="type_conversion",
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


def parse_date_column(
    df: pl.DataFrame,
    column: str,
    error_collector: ErrorCollector,
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
        error_collector: ErrorCollector instance to track failures
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with parsed date column

    Example:
        >>> df = parse_date_column(
        ...     df=df,
        ...     column="hba1c_updated_date",
        ...     error_collector=collector,
        ... )
    """
    if column not in df.columns:
        return df

    # Store original values for error reporting
    df = df.with_columns(pl.col(column).alias(f"_orig_{column}"))

    # Apply parse_date_flexible to each value
    # NOTE: Using list-based approach instead of map_elements() because
    # map_elements() with return_dtype=pl.Date fails when ALL values are None
    # (all-NA columns like hospitalisation_date).
    # Explicit Series creation with dtype=pl.Date works because it doesn't
    # require non-null values.
    column_values = df[column].cast(pl.Utf8).to_list()
    parsed_dates = [
        parse_date_flexible(val, error_val=settings.error_val_date) for val in column_values
    ]
    parsed_series = pl.Series(f"_parsed_{column}", parsed_dates, dtype=pl.Date)
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
            error_collector.add_error(
                file_name=row.get(file_name_col) or "unknown",
                patient_id=row.get(patient_id_col) or "unknown",
                column=column,
                original_value=row[f"_orig_{column}"],
                error_message="Could not parse date",
                error_code="type_conversion",
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
    error_collector: ErrorCollector,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Replace out-of-range numeric values with error value.

    Args:
        df: Input DataFrame
        column: Column name to check
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        error_collector: ErrorCollector instance to track violations
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
        ...     error_collector=collector,
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
            error_collector.add_error(
                file_name=row.get(file_name_col) or "unknown",
                patient_id=row.get(patient_id_col) or "unknown",
                column=column,
                original_value=row[column],
                error_message=f"Value {row[column]} outside allowed range [{min_val}, {max_val}]",
                error_code="invalid_value",
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
    error_collector: ErrorCollector,
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
        error_collector: ErrorCollector instance
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
        ...     error_collector=collector,
        ... )
    """
    for column in columns:
        df = safe_convert_column(
            df=df,
            column=column,
            target_type=target_type,
            error_collector=error_collector,
            error_value=error_value,
            file_name_col=file_name_col,
            patient_id_col=patient_id_col,
        )

    return df
