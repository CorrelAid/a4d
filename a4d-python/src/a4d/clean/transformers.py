"""Data transformation functions for cleaning.

This module provides transformation functions that are applied before validation.
These functions standardize values, fix legacy formats, and normalize data.

Transformations are referenced in reference_data/data_cleaning.yaml with
type: basic_function.
"""

import polars as pl
import re


def extract_regimen(df: pl.DataFrame, column: str = "insulin_regimen") -> pl.DataFrame:
    """Extract and standardize insulin regimen values.

    This function applies regex pattern matching to standardize insulin regimen
    descriptions into canonical forms. Matches are case-insensitive.

    Transformations:
    - Contains "basal" → "Basal-bolus (MDI)"
    - Contains "premixed" → "Premixed 30/70 BD"
    - Contains "self-mixed" → "Self-mixed BD"
    - Contains "conventional" → "Modified conventional TID"

    Args:
        df: Input DataFrame
        column: Column name to transform (default: "insulin_regimen")

    Returns:
        DataFrame with standardized insulin regimen values

    Example:
        >>> df = extract_regimen(df)
        >>> # "Basal-bolus" → "Basal-bolus (MDI)"
        >>> # "PREMIXED 30/70" → "Premixed 30/70 BD"
    """
    if column not in df.columns:
        return df

    # Apply regex transformations in order (matching R's behavior)
    df = df.with_columns(
        pl.col(column)
        .str.to_lowercase()
        .str.replace(r"^.*basal.*$", "Basal-bolus (MDI)")
        .str.replace(r"^.*premixed.*$", "Premixed 30/70 BD")
        .str.replace(r"^.*self-mixed.*$", "Self-mixed BD")
        .str.replace(r"^.*conventional.*$", "Modified conventional TID")
        .alias(column)
    )

    return df


def str_to_lower(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Convert column values to lowercase.

    This is used for case-insensitive validation. For example, the "status"
    column may have mixed case values like "Active", "ACTIVE", "active" which
    should all be normalized to lowercase before validation.

    Args:
        df: Input DataFrame
        column: Column name to transform

    Returns:
        DataFrame with lowercase column values

    Example:
        >>> df = str_to_lower(df, "status")
        >>> # "ACTIVE" → "active"
        >>> # "Inactive" → "inactive"
    """
    if column not in df.columns:
        return df

    df = df.with_columns(pl.col(column).str.to_lowercase().alias(column))

    return df


def apply_transformation(
    df: pl.DataFrame,
    column: str,
    function_name: str,
) -> pl.DataFrame:
    """Apply a named transformation function to a column.

    This is the dispatcher function that maps function names from
    data_cleaning.yaml to actual transformation functions.

    Args:
        df: Input DataFrame
        column: Column name to transform
        function_name: Name of transformation function (from YAML)

    Returns:
        DataFrame with transformation applied

    Raises:
        ValueError: If function_name is not recognized

    Example:
        >>> df = apply_transformation(df, "status", "stringr::str_to_lower")
        >>> df = apply_transformation(df, "insulin_regimen", "extract_regimen")
    """
    # Map R function names to Python implementations
    function_mapping = {
        "extract_regimen": lambda df, col: extract_regimen(df, col),
        "stringr::str_to_lower": lambda df, col: str_to_lower(df, col),
        "str_to_lower": lambda df, col: str_to_lower(df, col),
    }

    if function_name not in function_mapping:
        raise ValueError(f"Unknown transformation function: {function_name}")

    return function_mapping[function_name](df, column)


def correct_decimal_sign_multiple(
    df: pl.DataFrame,
    columns: list[str],
) -> pl.DataFrame:
    """Replace comma decimal separator with dot for multiple columns.

    Some trackers use European decimal format (1,5 instead of 1.5).
    This function fixes that for multiple numeric columns.

    Args:
        df: Input DataFrame
        columns: List of column names to correct

    Returns:
        DataFrame with corrected decimal signs

    Example:
        >>> df = correct_decimal_sign_multiple(df, ["weight", "height", "hba1c"])
    """
    from a4d.clean.converters import correct_decimal_sign

    for column in columns:
        df = correct_decimal_sign(df, column)

    return df
