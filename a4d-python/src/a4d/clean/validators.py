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

from a4d.config import settings
from a4d.errors import ErrorCollector
from a4d.reference.loaders import load_yaml, get_reference_data_path


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
    """Validate column against allowed values.

    Args:
        df: Input DataFrame
        column: Column name to validate
        allowed_values: List of allowed string values
        error_collector: ErrorCollector instance to track violations
        replace_invalid: If True, replace invalid values with error value
        file_name_col: Column containing file name for error tracking
        patient_id_col: Column containing patient ID for error tracking

    Returns:
        DataFrame with invalid values replaced (if replace_invalid=True)

    Example:
        >>> collector = ErrorCollector()
        >>> df = validate_allowed_values(
        ...     df=df,
        ...     column="status",
        ...     allowed_values=["Active", "Inactive"],
        ...     error_collector=collector,
        ...     replace_invalid=True,
        ... )
    """
    if column not in df.columns:
        return df

    # Find invalid values (not in allowed list, not null, not already error value)
    invalid_mask = (
        pl.col(column).is_not_null()
        & (pl.col(column) != settings.error_val_character)
        & (~pl.col(column).is_in(allowed_values))
    )

    # Extract invalid rows for error logging
    invalid_rows = df.filter(invalid_mask)

    # Log each invalid value
    if len(invalid_rows) > 0:
        for row in invalid_rows.iter_rows(named=True):
            error_collector.add_error(
                file_name=row.get(file_name_col, "unknown"),
                patient_id=row.get(patient_id_col, "unknown"),
                column=column,
                original_value=row[column],
                error_message=f"Value '{row[column]}' not in allowed values: {allowed_values}",
                error_code="invalid_value",
                function_name="validate_allowed_values",
            )

    # Replace invalid values with error value if configured
    if replace_invalid:
        df = df.with_columns(
            pl.when(invalid_mask)
            .then(pl.lit(settings.error_val_character))
            .otherwise(pl.col(column))
            .alias(column)
        )

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

    return df
