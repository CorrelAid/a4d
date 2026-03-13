"""Data transformation functions for cleaning.

This module provides transformation functions that are applied before validation.
These functions standardize values, fix legacy formats, and normalize data.

Transformations are referenced in reference_data/data_cleaning.yaml with
type: basic_function.
"""

import polars as pl

from a4d.config import settings


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


def fix_sex(df: pl.DataFrame, column: str = "sex") -> pl.DataFrame:
    """Map sex synonyms to canonical values (M/F) or error value.

    Matches R's fix_sex() function behavior:
    - Female synonyms: female, girl, woman, fem, feminine, f → "F"
    - Male synonyms: male, boy, man, masculine, m → "M"
    - Anything else → "Undefined" (error value)

    Args:
        df: Input DataFrame
        column: Column name to transform (default: "sex")

    Returns:
        DataFrame with sex values normalized to M/F or Undefined

    Example:
        >>> df = fix_sex(df)
        >>> # "Female" → "F"
        >>> # "MALE" → "M"
        >>> # "invalid" → "Undefined"
    """
    if column not in df.columns:
        return df

    # Define synonyms matching R's fix_sex function
    synonyms_female = ["female", "girl", "woman", "fem", "feminine", "f"]
    synonyms_male = ["male", "boy", "man", "masculine", "m"]

    # Build expression using pl.when().then().when().then()... chain
    # Start with null/empty handling
    expr = pl.when(pl.col(column).is_null() | (pl.col(column) == "")).then(None)

    # Add female synonyms
    for synonym in synonyms_female:
        expr = expr.when(pl.col(column).str.to_lowercase() == synonym).then(pl.lit("F"))

    # Add male synonyms
    for synonym in synonyms_male:
        expr = expr.when(pl.col(column).str.to_lowercase() == synonym).then(pl.lit("M"))

    # Default: anything else becomes Undefined
    expr = expr.otherwise(pl.lit(settings.error_val_character))

    df = df.with_columns(expr.alias(column))

    return df


def fix_bmi(df: pl.DataFrame) -> pl.DataFrame:
    """Calculate BMI from weight and height.

    Matches R's fix_bmi() function behavior:
    - If weight or height is null → BMI becomes null
    - If weight or height is error value → BMI becomes error value
    - Otherwise: BMI = weight / height^2

    Height is converted from cm to m if > 50 (R's transform_cm_to_m threshold).
    This ensures correct BMI regardless of whether height is in cm or m.

    This calculation REPLACES any existing BMI value, matching R's behavior.

    Args:
        df: Input DataFrame (must have weight and height columns)

    Returns:
        DataFrame with calculated BMI column

    Example:
        >>> df = fix_bmi(df)
        >>> # weight=70, height=1.75 → bmi=22.86
        >>> # weight=30.7, height=135.5 (cm) → height_m=1.355, bmi=16.72
    """
    if "weight" not in df.columns or "height" not in df.columns:
        return df

    # Convert height from cm to m if > 50 (R's transform_cm_to_m threshold)
    height_m = (
        pl.when(pl.col("height") > 50).then(pl.col("height") / 100.0).otherwise(pl.col("height"))
    )

    # Calculate BMI: weight / height^2
    # Match R's case_when logic exactly
    df = df.with_columns(
        pl.when(pl.col("weight").is_null() | pl.col("height").is_null())
        .then(None)
        .when(
            (pl.col("weight") == settings.error_val_numeric)
            | (pl.col("height") == settings.error_val_numeric)
        )
        .then(pl.lit(settings.error_val_numeric))
        .otherwise(pl.col("weight") / height_m.pow(2))
        .alias("bmi")
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


def replace_range_with_mean(x: str) -> float:
    """Calculate mean of a range string.

    Matches R's replace_range_with_mean() function behavior.
    Splits string on "-", converts parts to numeric, returns mean.

    Args:
        x: Range string (e.g., "0-2", "2-3")

    Returns:
        Mean of the range values

    Example:
        >>> replace_range_with_mean("0-2")
        1.0
        >>> replace_range_with_mean("2-3")
        2.5
    """
    parts = x.split("-")
    numbers = [float(p) for p in parts]
    return sum(numbers) / len(numbers)


def fix_testing_frequency(df: pl.DataFrame) -> pl.DataFrame:
    """Fix testing_frequency column by replacing ranges with mean values.

    Matches R's fix_testing_frequency() function behavior:
    - Replaces ranges like "0-2" with mean "1"
    - Preserves null and empty values as null
    - Logs warning when ranges are detected

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with testing_frequency ranges replaced by mean values

    Example:
        >>> df = fix_testing_frequency(df)
        >>> # "0-2" → "1"
        >>> # "2-3" → "2.5"
        >>> # "2" → "2" (unchanged)
    """
    if "testing_frequency" not in df.columns:
        return df

    from loguru import logger

    # Track if we logged warnings
    has_ranges = False

    def fix_value(value: str | None) -> str | None:
        """Fix a single testing_frequency value."""
        nonlocal has_ranges

        if value is None or value == "":
            return None

        if "-" in value:
            has_ranges = True

            try:
                mean_value = replace_range_with_mean(value)
                # Return as string, remove trailing .0 for whole numbers
                if mean_value == int(mean_value):
                    return str(int(mean_value))
                return str(mean_value)
            except Exception:
                # If replacement fails, return None
                return None

        return value

    # Apply transformation
    df = df.with_columns(
        pl.col("testing_frequency")
        .map_elements(fix_value, return_dtype=pl.String)
        .alias("testing_frequency")
    )

    # Log warning if any ranges were found
    if has_ranges:
        logger.bind(error_code="invalid_value").warning("Found ranges in testing_frequency column. Replacing with mean values.")

    return df


def split_bp_in_sys_and_dias(df: pl.DataFrame) -> pl.DataFrame:
    """Split blood_pressure_mmhg into systolic and diastolic columns.

    Matches R's split_bp_in_sys_and_dias() function behavior:
    - Splits "120/80" format into two columns
    - Invalid formats (without "/") are replaced with error value
    - Logs warning for invalid values

    Args:
        df: Input DataFrame with blood_pressure_mmhg column

    Returns:
        DataFrame with blood_pressure_sys_mmhg and blood_pressure_dias_mmhg columns

    Example:
        >>> df = split_bp_in_sys_and_dias(df)
        >>> # "96/55" → sys="96", dias="55"
        >>> # "96" → sys="999999", dias="999999" (invalid)
    """
    if "blood_pressure_mmhg" not in df.columns:
        return df

    from loguru import logger

    # First, replace invalid values (those without "/") with error format
    error_val_int = int(settings.error_val_numeric)
    df = df.with_columns(
        pl.when(~pl.col("blood_pressure_mmhg").str.contains("/", literal=True))
        .then(pl.lit(f"{error_val_int}/{error_val_int}"))
        .otherwise(pl.col("blood_pressure_mmhg"))
        .alias("blood_pressure_mmhg")
    )

    # Check if any invalid values were found
    error_pattern = f"{error_val_int}/{error_val_int}"
    has_errors = df.filter(pl.col("blood_pressure_mmhg") == error_pattern).height > 0

    if has_errors:
        logger.bind(error_code="invalid_value").warning(
            "Found invalid values for column blood_pressure_mmhg "
            f"that do not follow the format X/Y. "
            f"Values were replaced with {error_val_int}."
        )

    # Split the column
    df = df.with_columns(
        pl.col("blood_pressure_mmhg").str.split("/").list.get(0).alias("blood_pressure_sys_mmhg"),
        pl.col("blood_pressure_mmhg").str.split("/").list.get(1).alias("blood_pressure_dias_mmhg"),
    )

    # Drop the original combined column
    df = df.drop("blood_pressure_mmhg")

    return df
