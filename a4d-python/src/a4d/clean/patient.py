"""Patient data cleaning pipeline.

This module orchestrates the complete cleaning pipeline for patient data,
following the R pipeline's meta schema approach (script2_process_patient_data.R):

1. Load raw patient data
2. Apply legacy format fixes
3. Apply transformations
4. Type conversions
5. Validation
6. Apply meta schema (ensure all columns exist, consistent output)
"""

from pathlib import Path

import polars as pl
from loguru import logger

from a4d.clean.converters import (
    correct_decimal_sign,
    cut_numeric_value,
    safe_convert_column,
)
from a4d.clean.schema import (
    apply_schema,
    get_date_columns,
    get_numeric_columns,
    get_patient_data_schema,
)
from a4d.clean.transformers import extract_regimen, str_to_lower
from a4d.clean.validators import validate_all_columns
from a4d.config import settings
from a4d.errors import ErrorCollector


def clean_patient_data(
    df_raw: pl.DataFrame,
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """Clean raw patient data following the complete pipeline.

    This function orchestrates all cleaning steps and ensures the output
    conforms to the meta schema, regardless of which columns exist in input.

    Args:
        df_raw: Raw patient data from extraction
        error_collector: ErrorCollector instance for tracking errors

    Returns:
        Cleaned DataFrame with complete meta schema applied

    Example:
        >>> from a4d.extract.patient import extract_patient_data
        >>> from a4d.errors import ErrorCollector
        >>>
        >>> collector = ErrorCollector()
        >>> df_raw = extract_patient_data(tracker_file)
        >>> df_clean = clean_patient_data(df_raw, collector)
        >>> # df_clean has ALL schema columns, with consistent types
    """
    logger.info(f"Starting patient data cleaning: {len(df_raw)} rows, {len(df_raw.columns)} columns")

    # Step 1: Legacy format fixes
    df = _apply_legacy_fixes(df_raw)

    # Step 2: Pre-processing transformations
    df = _apply_preprocessing(df)

    # Step 3: Data transformations (regimen extraction, lowercasing, etc.)
    df = _apply_transformations(df)

    # Step 4: Apply meta schema EARLY (like R does) to ensure all columns exist before conversions
    # This allows unit conversions to work on columns that don't exist in raw data
    df = apply_schema(df)

    # Step 5: Type conversions
    df = _apply_type_conversions(df, error_collector)

    # Step 6: Range validation and cleanup
    df = _apply_range_validation(df, error_collector)

    # Step 7: Allowed values validation
    df = validate_all_columns(df, error_collector)

    # Step 8: Unit conversions (requires schema to be applied first!)
    df = _apply_unit_conversions(df)

    # Step 9: Create tracker_date from year/month
    df = _add_tracker_date(df)

    # Step 10: Sort by tracker_date and patient_id
    df = df.sort(["tracker_date", "patient_id"])

    logger.info(f"Cleaning complete: {len(df)} rows, {len(df.columns)} columns")
    logger.info(f"Errors collected: {len(error_collector)}")

    return df


def _apply_legacy_fixes(df: pl.DataFrame) -> pl.DataFrame:
    """Apply fixes for legacy tracker formats (pre-2024).

    Legacy trackers may have:
    - Combined date+value columns (e.g., hba1c_updated contains both)
    - Combined blood pressure values (sys/dias in one column)
    - Different column structures

    For now, we skip these complex legacy fixes and implement them
    when we encounter older trackers.

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with legacy fixes applied
    """
    # TODO: Implement when we process pre-2024 trackers:
    # - extract_date_from_measurement() for hba1c_updated, fbg_updated
    # - split_bp_in_sys_and_dias() for blood_pressure_mmhg

    return df


def _apply_preprocessing(df: pl.DataFrame) -> pl.DataFrame:
    """Apply preprocessing transformations before type conversion.

    This includes:
    - Removing > and < signs from HbA1c values (but tracking them)
    - Replacing "-" with "N" in Y/N columns
    - Deriving insulin_type and insulin_subtype from individual columns (2024+)

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with preprocessing applied
    """
    # Track HbA1c exceeds markers (> or <)
    if "hba1c_baseline" in df.columns:
        df = df.with_columns(pl.col("hba1c_baseline").str.contains(r"[><]").alias("hba1c_baseline_exceeds"))
        df = df.with_columns(pl.col("hba1c_baseline").str.replace_all(r"[><]", "").alias("hba1c_baseline"))

    if "hba1c_updated" in df.columns:
        df = df.with_columns(pl.col("hba1c_updated").str.contains(r"[><]").alias("hba1c_updated_exceeds"))
        df = df.with_columns(pl.col("hba1c_updated").str.replace_all(r"[><]", "").alias("hba1c_updated"))

    # Replace "-" with "N" in Y/N columns (2024+ trackers use "-" for No)
    yn_columns = [
        "analog_insulin_long_acting",
        "analog_insulin_rapid_acting",
        "human_insulin_intermediate_acting",
        "human_insulin_pre_mixed",
        "human_insulin_short_acting",
    ]

    for col in yn_columns:
        if col in df.columns:
            df = df.with_columns(pl.col(col).str.replace("-", "N").alias(col))

    # Derive insulin_type and insulin_subtype from individual columns (2024+)
    # R's validation will convert insulin_type to Title Case and insulin_subtype to "Undefined"
    if "human_insulin_pre_mixed" in df.columns:
        df = _derive_insulin_fields(df)

    return df


def _derive_insulin_fields(df: pl.DataFrame) -> pl.DataFrame:
    """Derive insulin_type and insulin_subtype from individual columns.

    For 2024+ trackers:
    - insulin_type: "Human Insulin" if any human column is Y, else "Analog Insulin"
    - insulin_subtype: Comma-separated list of subtype names where value is Y

    Args:
        df: Input DataFrame with individual insulin columns

    Returns:
        DataFrame with insulin_type and insulin_subtype derived
    """
    # Determine insulin_type
    df = df.with_columns(
        pl.when(
            (pl.col("human_insulin_pre_mixed") == "Y")
            | (pl.col("human_insulin_short_acting") == "Y")
            | (pl.col("human_insulin_intermediate_acting") == "Y")
        )
        .then(pl.lit("Human Insulin"))
        .otherwise(pl.lit("Analog Insulin"))
        .alias("insulin_type")
    )

    # Build insulin_subtype as comma-separated list
    # This is complex in Polars - we build a list and join
    df = df.with_columns(
        pl.concat_list(
            [
                pl.when(pl.col("human_insulin_pre_mixed") == "Y").then(pl.lit("Pre-mixed")).otherwise(pl.lit(None)),
                pl.when(pl.col("human_insulin_short_acting") == "Y")
                .then(pl.lit("Short-acting"))
                .otherwise(pl.lit(None)),
                pl.when(pl.col("human_insulin_intermediate_acting") == "Y")
                .then(pl.lit("Intermediate-acting"))
                .otherwise(pl.lit(None)),
                pl.when(pl.col("analog_insulin_rapid_acting") == "Y")
                .then(pl.lit("Rapid-acting"))
                .otherwise(pl.lit(None)),
                pl.when(pl.col("analog_insulin_long_acting") == "Y")
                .then(pl.lit("Long-acting"))
                .otherwise(pl.lit(None)),
            ]
        )
        .list.drop_nulls()
        .list.join(",")
        .alias("insulin_subtype")
    )

    return df


def _apply_transformations(df: pl.DataFrame) -> pl.DataFrame:
    """Apply data transformations.

    Transformations are explicit Python code (not config-driven):
    - Lowercase status for case-insensitive validation
    - Standardize insulin regimen descriptions
    - Correct European decimal format

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with transformations applied
    """
    # Status should keep original case to match R pipeline
    # R validation is case-insensitive but preserves original values

    # Standardize insulin regimen
    if "insulin_regimen" in df.columns:
        df = extract_regimen(df)

    # Correct European decimal format (comma → dot)
    numeric_cols = [
        "hba1c_baseline",
        "hba1c_updated",
        "fbg_updated_mg",
        "fbg_updated_mmol",
        "weight",
        "height",
        "bmi",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df = correct_decimal_sign(df, col)

    return df


def _apply_type_conversions(df: pl.DataFrame, error_collector: ErrorCollector) -> pl.DataFrame:
    """Convert columns to target types using safe_convert_column.

    Only converts columns that exist in both the DataFrame and the schema.

    Special handling:
    - Date columns: Strip time component from datetime strings
    - Integer columns: Convert via Float64 first to handle decimals

    Args:
        df: Input DataFrame
        error_collector: ErrorCollector for tracking conversion failures

    Returns:
        DataFrame with types converted
    """
    schema = get_patient_data_schema()

    # Convert each column that exists
    for col, target_type in schema.items():
        if col not in df.columns:
            continue

        # Skip if already the correct type (happens when schema adds NULL columns)
        if df[col].dtype == target_type:
            continue

        # Special handling for Date columns: strip time component from datetime strings
        if target_type == pl.Date:
            df = df.with_columns(
                pl.col(col).str.slice(0, 10).alias(col)  # Take first 10 chars: "2009-04-17"
            )

        # Special handling for Int32: convert via Float64 first (handles "14.0" → 14.0 → 14)
        if target_type == pl.Int32:
            df = safe_convert_column(df, col, pl.Float64, error_collector)
            df = df.with_columns(pl.col(col).round(0).cast(pl.Int32, strict=False).alias(col))
        else:
            df = safe_convert_column(
                df=df,
                column=col,
                target_type=target_type,
                error_collector=error_collector,
            )

    return df


def _apply_range_validation(df: pl.DataFrame, error_collector: ErrorCollector) -> pl.DataFrame:
    """Apply range validation and value cleanup.

    This includes:
    - Height: 0-2.3m (convert cm to m if needed)
    - Weight: 0-200kg
    - BMI: 4-60
    - Age: 0-25 years
    - HbA1c: 4-18%
    - FBG: 0-136.5 mmol/l

    Args:
        df: Input DataFrame
        error_collector: ErrorCollector for tracking violations

    Returns:
        DataFrame with range validation applied
    """
    # Height: convert cm to m if > 2.3 (likely in cm), then validate
    if "height" in df.columns:
        df = df.with_columns(
            pl.when(pl.col("height") > 2.3).then(pl.col("height") / 100.0).otherwise(pl.col("height")).alias("height")
        )
        df = cut_numeric_value(df, "height", 0, 2.3, error_collector)

    # Weight: 0-200 kg
    if "weight" in df.columns:
        df = cut_numeric_value(df, "weight", 0, 200, error_collector)

    # BMI: 4-60
    if "bmi" in df.columns:
        df = cut_numeric_value(df, "bmi", 4, 60, error_collector)

    # Age: 0-25 years
    if "age" in df.columns:
        df = cut_numeric_value(df, "age", 0, 25, error_collector)

    # HbA1c baseline: 4-18%
    if "hba1c_baseline" in df.columns:
        df = cut_numeric_value(df, "hba1c_baseline", 4, 18, error_collector)

    # HbA1c updated: 4-18%
    if "hba1c_updated" in df.columns:
        df = cut_numeric_value(df, "hba1c_updated", 4, 18, error_collector)

    # FBG updated mmol: 0-136.5 (world record)
    if "fbg_updated_mmol" in df.columns:
        df = cut_numeric_value(df, "fbg_updated_mmol", 0, 136.5, error_collector)

    return df


def _apply_unit_conversions(df: pl.DataFrame) -> pl.DataFrame:
    """Apply unit conversions.

    - FBG mmol/l ↔ mg/dl conversion (18x factor)
    - Only convert if one is missing but the other exists

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with unit conversions applied
    """
    # Convert fbg_updated_mg to mmol if mmol is all NULL
    if "fbg_updated_mmol" in df.columns and "fbg_updated_mg" in df.columns:
        if df["fbg_updated_mmol"].is_null().all():
            df = df.with_columns(
                pl.when(pl.col("fbg_updated_mg") != settings.error_val_numeric)
                .then(pl.col("fbg_updated_mg") / 18.0)
                .otherwise(None)
                .alias("fbg_updated_mmol")
            )

    # Convert fbg_updated_mmol to mg if mg is all NULL
    if "fbg_updated_mg" in df.columns and "fbg_updated_mmol" in df.columns:
        if df["fbg_updated_mg"].is_null().all():
            df = df.with_columns(
                pl.when(pl.col("fbg_updated_mmol") != settings.error_val_numeric)
                .then(pl.col("fbg_updated_mmol") * 18.0)
                .otherwise(None)
                .alias("fbg_updated_mg")
            )

    return df


def _add_tracker_date(df: pl.DataFrame) -> pl.DataFrame:
    """Create tracker_date from tracker_year and tracker_month.

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with tracker_date column
    """
    if "tracker_year" in df.columns and "tracker_month" in df.columns:
        # Parse year-month to date (first day of month)
        # Cast to string first since they're now Int32
        df = df.with_columns(
            pl.concat_str([
                pl.col("tracker_year").cast(pl.String),
                pl.lit("-"),
                pl.col("tracker_month").cast(pl.String),
                pl.lit("-01")
            ])
            .str.to_date("%Y-%m-%d")
            .alias("tracker_date")
        )

    return df


def clean_patient_file(
    raw_parquet_path: Path,
    output_parquet_path: Path,
    error_collector: ErrorCollector | None = None,
) -> None:
    """Clean a single patient data parquet file.

    This is the main entry point for cleaning a tracker file.

    Args:
        raw_parquet_path: Path to raw patient parquet (from extraction)
        output_parquet_path: Path to write cleaned parquet
        error_collector: Optional ErrorCollector (creates new one if not provided)

    Example:
        >>> from pathlib import Path
        >>> raw_path = Path("output/patient_data_raw/2024_Hospital_patient_raw.parquet")
        >>> clean_path = Path("output/patient_data_clean/2024_Hospital_patient_clean.parquet")
        >>> clean_patient_file(raw_path, clean_path)
    """
    if error_collector is None:
        error_collector = ErrorCollector()

    logger.info(f"Cleaning patient file: {raw_parquet_path}")

    # Read raw parquet
    df_raw = pl.read_parquet(raw_parquet_path)

    # Clean data
    df_clean = clean_patient_data(df_raw, error_collector)

    # Create output directory if needed
    output_parquet_path.parent.mkdir(parents=True, exist_ok=True)

    # Write cleaned parquet
    df_clean.write_parquet(output_parquet_path)

    logger.info(f"Cleaned patient file written: {output_parquet_path}")
    logger.info(f"Total errors: {len(error_collector)}")
