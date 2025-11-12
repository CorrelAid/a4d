"""Schema and validation utilities for data cleaning.

This module provides functions for validating DataFrame columns against
allowed values defined in reference_data/validation_rules.yaml.

The validation pattern is:
1. Load validation rules from YAML
2. Check column values against allowed values
3. Log invalid values to ErrorCollector
4. Replace invalid values with error value (if configured)

Note: Data transformations are NOT in the YAML - they are hardcoded in
transformers.py for better type safety and maintainability.
"""

import polars as pl
from typing import Any
import re

from a4d.config import settings
from a4d.errors import ErrorCollector
from a4d.reference.loaders import load_yaml, get_reference_data_path


def sanitize_str(text: str) -> str:
    """Sanitize string for case-insensitive matching.

    Matches R's sanitize_str function:
    1. Convert to lowercase
    2. Remove spaces
    3. Remove special characters (keep only alphanumeric)

    Args:
        text: String to sanitize

    Returns:
        Sanitized string

    Example:
        >>> sanitize_str("Active - Remote")
        'activeremote'
        >>> sanitize_str("Lost Follow Up")
        'lostfollowup'
    """
    if not isinstance(text, str):
        return text
    return re.sub(r'[^a-z0-9]', '', text.lower())


def load_validation_rules() -> dict[str, Any]:
    """Load validation rules from validation_rules.yaml.

    Returns:
        Dictionary mapping column names to their validation rules.
        Structure: {column_name: {allowed_values: [...], replace_invalid: bool}}

    Example:
        >>> rules = load_validation_rules()
        >>> rules["status"]["allowed_values"]
        ['active', 'inactive', ...]
        >>> rules["status"]["replace_invalid"]
        True
    """
    yaml_path = get_reference_data_path("validation_rules.yaml")
    return load_yaml(yaml_path)


def validate_allowed_values(
    df: pl.DataFrame,
    column: str,
    allowed_values: list[str],
    error_collector: ErrorCollector,
    replace_invalid: bool = True,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Validate column against allowed values with case-insensitive matching.

    Matches R's validation behavior:
    1. Sanitize both input values and allowed values for matching
    2. If matched, replace with canonical value from allowed_values
    3. If not matched, replace with error value (if replace_invalid=True)

    Args:
        df: Input DataFrame
        column: Column name to validate
        allowed_values: List of canonical allowed values (e.g., ["Active", "Inactive"])
        error_collector: ErrorCollector instance to track violations
        replace_invalid: If True, replace invalid values with error value
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with values normalized to canonical form or replaced

    Example:
        >>> collector = ErrorCollector()
        >>> df = validate_allowed_values(
        ...     df=df,
        ...     column="status",
        ...     allowed_values=["Active", "Inactive"],  # Canonical forms
        ...     error_collector=collector,
        ... )
        >>> # "active", "ACTIVE", "Active" all become "Active"
    """
    if column not in df.columns:
        return df

    # Create mapping: {sanitized → canonical} like R does
    # E.g., {"active": "Active", "activeremote": "Active - Remote"}
    canonical_mapping = {sanitize_str(val): val for val in allowed_values}

    # Get unique non-null values from the column
    col_values = df.filter(pl.col(column).is_not_null()).select(column).unique()

    # Track which values need replacement and their canonical forms
    value_replacements = {}  # {original → canonical or error_value}

    for row in col_values.iter_rows(named=True):
        original_val = row[column]

        # Skip if already the error value
        if original_val == settings.error_val_character:
            value_replacements[original_val] = original_val
            continue

        # Sanitize and lookup
        sanitized = sanitize_str(original_val)

        if sanitized in canonical_mapping:
            # Valid - replace with canonical value
            value_replacements[original_val] = canonical_mapping[sanitized]
        else:
            # Invalid - log error
            error_collector.add_error(
                file_name="unknown",  # Will be filled in bulk operations
                patient_id="unknown",
                column=column,
                original_value=original_val,
                error_message=f"Value '{original_val}' not in allowed values: {allowed_values}",
                error_code="invalid_value",
                function_name="validate_allowed_values",
            )

            if replace_invalid:
                value_replacements[original_val] = settings.error_val_character
            else:
                value_replacements[original_val] = original_val

    # Apply all replacements at once using pl.when().then() chain
    # This ensures we replace with canonical values even if they match
    if value_replacements:
        expr = pl.col(column)
        for original, replacement in value_replacements.items():
            expr = pl.when(pl.col(column) == original).then(pl.lit(replacement)).otherwise(expr)

        df = df.with_columns(expr.alias(column))

    return df


def validate_column_from_rules(
    df: pl.DataFrame,
    column: str,
    rules: dict[str, Any],
    error_collector: ErrorCollector,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Validate column using rules from validation_rules.yaml.

    Args:
        df: Input DataFrame
        column: Column name to validate
        rules: Validation rules for this column (from validation_rules.yaml)
                Structure: {allowed_values: [...], replace_invalid: bool}
        error_collector: ErrorCollector instance
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with column validated and cleaned

    Example:
        >>> rules = load_validation_rules()
        >>> collector = ErrorCollector()
        >>> df = validate_column_from_rules(
        ...     df=df,
        ...     column="status",
        ...     rules=rules["status"],
        ...     error_collector=collector,
        ... )
    """
    if column not in df.columns:
        return df

    # Extract validation parameters from simplified rules
    allowed_values = rules.get("allowed_values", [])
    replace_invalid = rules.get("replace_invalid", True)

    df = validate_allowed_values(
        df=df,
        column=column,
        allowed_values=allowed_values,
        error_collector=error_collector,
        replace_invalid=replace_invalid,
        file_name_col=file_name_col,
        patient_id_col=patient_id_col,
    )

    return df


def validate_province(
    df: pl.DataFrame,
    error_collector: ErrorCollector,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Validate province column against allowed provinces from YAML.

    Uses the shared allowed_provinces.yaml file to validate province values.
    Matches R's behavior: sanitizes values for comparison and sets invalid
    provinces to "Undefined".

    Args:
        df: Input DataFrame
        error_collector: ErrorCollector instance
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with province validated

    Example:
        >>> collector = ErrorCollector()
        >>> df = validate_province(df, collector)
    """
    from a4d.reference.provinces import load_canonical_provinces

    if "province" not in df.columns:
        return df

    # Load canonical province names (with proper casing) for validation
    allowed_provinces = load_canonical_provinces()

    # Use generic validator with loaded provinces
    df = validate_allowed_values(
        df=df,
        column="province",
        allowed_values=allowed_provinces,
        error_collector=error_collector,
        replace_invalid=True,
        file_name_col=file_name_col,
        patient_id_col=patient_id_col,
    )

    return df


def validate_all_columns(
    df: pl.DataFrame,
    error_collector: ErrorCollector,
    file_name_col: str = "file_name",
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Validate all columns that have rules in data_cleaning.yaml.

    Args:
        df: Input DataFrame
        error_collector: ErrorCollector instance
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with all columns validated

    Example:
        >>> collector = ErrorCollector()
        >>> df_clean = validate_all_columns(df, collector)
        >>> len(collector)  # Number of validation errors found
    """
    rules = load_validation_rules()

    for column, column_rules in rules.items():
        if column in df.columns:
            df = validate_column_from_rules(
                df=df,
                column=column,
                rules=column_rules,
                error_collector=error_collector,
                file_name_col=file_name_col,
                patient_id_col=patient_id_col,
            )

    # Validate province separately (not in validation_rules.yaml)
    df = validate_province(
        df=df,
        error_collector=error_collector,
        file_name_col=file_name_col,
        patient_id_col=patient_id_col,
    )

    # Fix patient_id LAST (other functions use it for logging)
    df = fix_patient_id(
        df=df,
        error_collector=error_collector,
        patient_id_col=patient_id_col,
    )

    return df


def fix_patient_id(
    df: pl.DataFrame,
    error_collector: ErrorCollector,
    patient_id_col: str = "patient_id",
) -> pl.DataFrame:
    """Validate and fix patient ID format.

    Matches R's fix_id() function behavior:
    - Valid format: XX_YY### (e.g., "KD_QB004")
      - 2 uppercase letters, underscore, 2 uppercase letters, 3 digits
    - Normalizes hyphens to underscores: "KD-QB004" → "KD_QB004"
    - Truncates if > 8 characters: "KD_QB004XY" → "KD_QB004"
    - Replaces with error value if ≤ 8 chars and invalid format

    This function should be called LAST in the validation pipeline because
    other functions use patient_id for error logging.

    Args:
        df: Input DataFrame
        error_collector: ErrorCollector for tracking validation errors
        patient_id_col: Column name for patient ID (default: "patient_id")

    Returns:
        DataFrame with validated/fixed patient IDs

    Example:
        >>> df = fix_patient_id(df, error_collector)
        >>> # "KD_QB004" → "KD_QB004" (valid)
        >>> # "KD-QB004" → "KD_QB004" (normalized)
        >>> # "KD_QB004XY" → "KD_QB004" (truncated)
        >>> # "INVALID" → "Other" (replaced)
    """
    import re

    from a4d.config import settings

    if patient_id_col not in df.columns:
        return df

    # Store original values for error reporting
    original_col = f"{patient_id_col}_original"
    df = df.with_columns(pl.col(patient_id_col).alias(original_col))

    # Valid format: XX_YY### (2 letters, underscore, 2 letters, 3 digits)
    valid_pattern = re.compile(r"^[A-Z]{2}_[A-Z]{2}\d{3}$")

    def fix_single_id(patient_id: str | None) -> str | None:
        """Fix a single patient ID value."""
        if patient_id is None:
            return None

        # Step 1: Replace hyphens with underscores
        patient_id = patient_id.replace("-", "_")

        # Step 2: Check if it matches the valid pattern
        if valid_pattern.match(patient_id):
            return patient_id

        # Step 3: Invalid format - either truncate or replace
        if len(patient_id) > 8:
            # Truncate to 8 characters
            return patient_id[:8]
        else:
            # Replace with error value
            return settings.error_val_character

    # Apply transformation
    df = df.with_columns(pl.col(patient_id_col).map_elements(fix_single_id, return_dtype=pl.String).alias(patient_id_col))

    # Now collect errors for changed values
    for row in df.iter_rows(named=True):
        original = row[original_col]
        fixed = row[patient_id_col]

        if original != fixed and original is not None:
            # Normalize original to check if it's just hyphen replacement
            normalized = original.replace("-", "_")

            if normalized != fixed:
                # Not just normalization - either truncation or replacement
                if len(original.replace("-", "_")) > 8:
                    # Truncation
                    error_collector.add_error(
                        file_name="",
                        patient_id=original,
                        column=patient_id_col,
                        original_value=original,
                        error_message=f"Patient ID truncated (length > 8)",
                        error_code="invalid_value",
                    )
                else:
                    # Replacement
                    error_collector.add_error(
                        file_name="",
                        patient_id=original,
                        column=patient_id_col,
                        original_value=original,
                        error_message=f"Invalid patient ID format (expected XX_YY###)",
                        error_code="invalid_value",
                    )

    # Drop the temporary column
    df = df.drop(original_col)

    return df
