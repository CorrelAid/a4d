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
    parse_date_column,
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

    # Step 5.5: Fix age from DOB (like R pipeline does)
    # Must happen after type conversions so DOB is a proper date
    # Must happen before range validation so validated age is correct
    df = _fix_age_from_dob(df, error_collector)

    # Step 5.6: Validate dates (replace future dates with error value)
    # Must happen after type conversions so dates are proper date types
    df = _validate_dates(df, error_collector)

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


def _extract_date_from_measurement(df: pl.DataFrame, col_name: str) -> pl.DataFrame:
    """Extract date from measurement values in legacy trackers.

    Matches R's extract_date_from_measurement() (script2_helper_patient_data_fix.R:115).

    For pre-2019 trackers, values and dates are combined in format:
    - "14.5 (Jan-20)" → value="14.5 ", date="Jan-20"
    - ">14 (Mar-18)" → value=">14 ", date="Mar-18"
    - "148 mg/dl   (Mar-18)" → value="148 mg/dl   ", date="Mar-18"

    Args:
        df: Input DataFrame
        col_name: Column name containing combined value+date

    Returns:
        DataFrame with extracted date in {col_name}_date column
    """
    if col_name not in df.columns:
        return df

    date_col_name = col_name.replace("_mg", "").replace("_mmol", "") + "_date"

    # Check if date column already exists (2019+ trackers)
    if date_col_name in df.columns:
        return df

    # Extract value before '(' and date between '(' and ')'
    # Using regex: everything before '(', then '(', then capture date, then optional ')'
    df = df.with_columns([
        # Extract value (everything before parenthesis, or entire value if no parenthesis)
        pl.col(col_name).str.extract(r"^([^(]+)", 1).str.strip_chars().alias(col_name),
        # Extract date (everything between parentheses, if present)
        pl.col(col_name).str.extract(r"\(([^)]+)\)", 1).alias(date_col_name)
    ])

    logger.debug(f"Extracted date from {col_name} into {date_col_name}")

    return df


def _apply_legacy_fixes(df: pl.DataFrame) -> pl.DataFrame:
    """Apply fixes for legacy tracker formats (pre-2024).

    Legacy trackers may have:
    - Combined date+value columns (e.g., hba1c_updated contains both)
    - Combined blood pressure values (sys/dias in one column)
    - Different column structures

    Matches R's legacy handling in script2_process_patient_data.R:30-66.

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with legacy fixes applied
    """
    # Extract dates from measurement columns for pre-2019 trackers
    # R checks if *_date column exists, if not, extracts from measurement column
    df = _extract_date_from_measurement(df, "hba1c_updated")
    df = _extract_date_from_measurement(df, "fbg_updated_mg")
    df = _extract_date_from_measurement(df, "fbg_updated_mmol")

    # TODO: Implement split_bp_in_sys_and_dias() for blood_pressure_mmhg when needed

    return df


def _fix_fbg_column(col: pl.Expr) -> pl.Expr:
    """Fix FBG column text values to numeric equivalents.

    Matches R's fix_fbg() function (script2_helper_patient_data_fix.R:551-567).
    Converts qualitative text to numeric values and removes DKA markers.

    Conversions (based on CDC guidelines):
    - "high", "bad", "hi", "hight" (typo) → "200"
    - "medium", "med" → "170"
    - "low", "good", "okay" → "140"
    - Remove "(DKA)" text, "mg/dl", "mmol/l" suffixes
    - Trim whitespace

    Args:
        col: Polars expression for FBG column

    Returns:
        Polars expression with fixed values
    """
    return (
        col.str.to_lowercase()
        # Remove unit suffixes (from legacy trackers like 2018)
        .str.replace_all(r"\s*mg/dl\s*", "", literal=False)
        .str.replace_all(r"\s*mmol/l\s*", "", literal=False)
        # Use case-when to match full words, not substrings
        .str.replace_all(r"^(high|hight|bad|hi)$", "200")  # Anchored to full string
        .str.replace_all(r"^(med|medium)$", "170")
        .str.replace_all(r"^(low|good|okay)$", "140")
        .str.replace_all(r"\(DKA\)", "", literal=True)
        .str.strip_chars()
    )


def _apply_preprocessing(df: pl.DataFrame) -> pl.DataFrame:
    """Apply preprocessing transformations before type conversion.

    This includes:
    - Normalizing patient_id (remove transfer clinic suffix)
    - Removing > and < signs from HbA1c values (but tracking them)
    - Fixing FBG text values (high/medium/low → numeric, removing (DKA))
    - Replacing "-" with "N" in Y/N columns
    - Deriving insulin_type and insulin_subtype from individual columns (2024+)

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with preprocessing applied
    """
    # Normalize patient_id: Keep only COUNTRY_ID part, remove transfer clinic suffix
    # Pattern: "MY_QH003_SB" → "MY_QH003" (keep first two underscore-separated parts)
    # This ensures consistent patient linking across years when patients transfer clinics
    if "patient_id" in df.columns:
        df = df.with_columns(
            pl.when(pl.col("patient_id").str.contains("_"))
            .then(pl.col("patient_id").str.extract(r"^([A-Z]+_[^_]+)", 1))
            .otherwise(pl.col("patient_id"))
            .alias("patient_id")
        )

    # Track HbA1c exceeds markers (> or <)
    if "hba1c_baseline" in df.columns:
        df = df.with_columns(
            pl.col("hba1c_baseline").str.contains(r"[><]").fill_null(False).alias("hba1c_baseline_exceeds")
        )
        df = df.with_columns(pl.col("hba1c_baseline").str.replace_all(r"[><]", "").alias("hba1c_baseline"))

    if "hba1c_updated" in df.columns:
        df = df.with_columns(
            pl.col("hba1c_updated").str.contains(r"[><]").fill_null(False).alias("hba1c_updated_exceeds")
        )
        df = df.with_columns(pl.col("hba1c_updated").str.replace_all(r"[><]", "").alias("hba1c_updated"))

    # Fix FBG text values (R: script2_helper_patient_data_fix.R:551-567)
    # Convert qualitative values to numeric: high→200, medium→170, low→140
    # Source: https://www.cdc.gov/diabetes/basics/getting-tested.html
    if "fbg_updated_mg" in df.columns:
        df = df.with_columns(_fix_fbg_column(pl.col("fbg_updated_mg")).alias("fbg_updated_mg"))

    if "fbg_updated_mmol" in df.columns:
        df = df.with_columns(_fix_fbg_column(pl.col("fbg_updated_mmol")).alias("fbg_updated_mmol"))

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

    Based on R's logic from script2_process_patient_data.R:91-111 but with corrections:
    - Uses lowercase values (R does this, validation converts to Title Case later)
    - FIXES R's typo: Uses "rapid-acting" (correct) instead of R's "rapic-acting" (typo)

    For 2024+ trackers:
    - insulin_type: "human insulin" if any human column is Y, else "analog insulin"
    - insulin_subtype: Comma-separated list like "pre-mixed,rapid-acting,long-acting"
      (will be replaced with "Undefined" by validation since comma-separated values aren't in allowed_values)

    NOTE: Python is CORRECT here. Comparison with R will show differences because R has a typo.

    Args:
        df: Input DataFrame with individual insulin columns

    Returns:
        DataFrame with insulin_type and insulin_subtype derived
    """
    # Determine insulin_type (lowercase to match R)
    # Important: R's ifelse returns NA when all conditions are NA/None
    # So we only derive insulin_type when at least one column is not None
    df = df.with_columns(
        pl.when(
            # Only derive if at least one insulin column is not null
            pl.col("human_insulin_pre_mixed").is_not_null()
            | pl.col("human_insulin_short_acting").is_not_null()
            | pl.col("human_insulin_intermediate_acting").is_not_null()
            | pl.col("analog_insulin_rapid_acting").is_not_null()
            | pl.col("analog_insulin_long_acting").is_not_null()
        )
        .then(
            # Now check which type
            pl.when(
                (pl.col("human_insulin_pre_mixed") == "Y")
                | (pl.col("human_insulin_short_acting") == "Y")
                | (pl.col("human_insulin_intermediate_acting") == "Y")
            )
            .then(pl.lit("human insulin"))
            .otherwise(pl.lit("analog insulin"))
        )
        .otherwise(None)  # Return None if all columns are None (matches R's NA)
        .alias("insulin_type")
    )

    # Build insulin_subtype as comma-separated list (lowercase to match R)
    # CORRECTED: Use "rapid-acting" (correct) instead of R's "rapic-acting" (typo)
    df = df.with_columns(
        pl.concat_list(
            [
                pl.when(pl.col("human_insulin_pre_mixed") == "Y").then(pl.lit("pre-mixed")).otherwise(pl.lit(None)),
                pl.when(pl.col("human_insulin_short_acting") == "Y")
                .then(pl.lit("short-acting"))
                .otherwise(pl.lit(None)),
                pl.when(pl.col("human_insulin_intermediate_acting") == "Y")
                .then(pl.lit("intermediate-acting"))
                .otherwise(pl.lit(None)),
                pl.when(pl.col("analog_insulin_rapid_acting") == "Y")
                .then(pl.lit("rapid-acting"))  # CORRECTED from R's typo
                .otherwise(pl.lit(None)),
                pl.when(pl.col("analog_insulin_long_acting") == "Y")
                .then(pl.lit("long-acting"))
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
    - Date columns: Use flexible date parser (handles Mar-18, Excel serials, etc.)
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

        # Special handling for Date columns: use flexible date parser
        if target_type == pl.Date:
            # Strip time component if present (e.g., "2009-04-17 00:00:00" → "2009-04-17")
            df = df.with_columns(
                pl.col(col).cast(pl.Utf8).str.slice(0, 10).alias(col)
            )
            # Use custom date parser for flexibility (handles Mar-18, Excel serials, etc.)
            df = parse_date_column(df, col, error_collector)
        # Special handling for Int32: convert via Float64 first (handles "14.0" → 14.0 → 14)
        elif target_type == pl.Int32:
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


def _fix_age_from_dob(df: pl.DataFrame, error_collector: ErrorCollector) -> pl.DataFrame:
    """Fix age by calculating from DOB and tracker date.

    Matches R pipeline's fix_age() function (script2_helper_patient_data_fix.R:329).
    Always uses calculated age from DOB rather than trusting Excel value.

    Logic:
    1. Calculate age: tracker_year - birth_year
    2. Adjust if birthday hasn't occurred yet: if tracker_month < birth_month: age -= 1
    3. If calculated age differs from Excel age, log warning and use calculated
    4. If calculated age is negative, use error value and log warning

    Args:
        df: DataFrame with age, dob, tracker_year, tracker_month, patient_id columns
        error_collector: ErrorCollector for tracking data quality issues

    Returns:
        DataFrame with corrected age values

    Example:
        >>> df = pl.DataFrame({
        ...     "patient_id": ["P001"],
        ...     "age": [21.0],  # Wrong value from Excel
        ...     "dob": [date(2006, 8, 8)],
        ...     "tracker_year": [2025],
        ...     "tracker_month": [2]
        ... })
        >>> collector = ErrorCollector()
        >>> fixed = _fix_age_from_dob(df, collector)
        >>> fixed["age"][0]  # Should be 18, not 21
        18.0
    """
    # Only fix if we have the necessary columns
    required_cols = ["age", "dob", "tracker_year", "tracker_month", "patient_id"]
    if not all(col in df.columns for col in required_cols):
        logger.debug("Skipping age fix: missing required columns")
        return df

    logger.info("Fixing age values from DOB (matching R pipeline logic)")

    # Calculate age from DOB
    # calc_age = tracker_year - year(dob)
    # if tracker_month < month(dob): calc_age -= 1
    df = df.with_columns(
        pl.when(pl.col("dob").is_not_null())
        .then(
            pl.col("tracker_year") - pl.col("dob").dt.year()
            - pl.when(pl.col("tracker_month") < pl.col("dob").dt.month()).then(1).otherwise(0)
        )
        .otherwise(None)
        .alias("_calc_age")
    )

    # Track which ages were fixed
    ages_fixed = 0
    ages_missing = 0
    ages_negative = 0

    # For each row where calc_age differs from age, log and fix
    for row in df.filter(
        pl.col("_calc_age").is_not_null()
        & ((pl.col("age").is_null()) | (pl.col("age") != pl.col("_calc_age")))
    ).iter_rows(named=True):
        patient_id = row["patient_id"]
        file_name = row.get("file_name", "unknown")
        excel_age = row["age"]
        calc_age = row["_calc_age"]

        if excel_age is None or (excel_age == settings.error_val_numeric):
            logger.warning(
                f"Patient {patient_id}: age is missing. "
                f"Using calculated age {calc_age} instead of original age."
            )
            error_collector.add_error(
                file_name=file_name,
                patient_id=patient_id,
                column="age",
                original_value=excel_age if excel_age is not None else "NULL",
                error_message=f"Age missing, calculated from DOB as {calc_age}",
                error_code="missing_value",
                function_name="_fix_age_from_dob"
            )
            ages_missing += 1
        elif calc_age < 0:
            logger.warning(
                f"Patient {patient_id}: calculated age is negative ({calc_age}). "
                f"Please check this manually. Using error value instead."
            )
            error_collector.add_error(
                file_name=file_name,
                patient_id=patient_id,
                column="age",
                original_value=str(excel_age),
                error_message=f"Calculated age is negative ({calc_age}), check DOB",
                error_code="invalid_value",
                function_name="_fix_age_from_dob"
            )
            ages_negative += 1
        else:
            logger.warning(
                f"Patient {patient_id}: age {excel_age} is different from calculated age {calc_age}. "
                f"Using calculated age instead of original age."
            )
            error_collector.add_error(
                file_name=file_name,
                patient_id=patient_id,
                column="age",
                original_value=str(excel_age),
                error_message=f"Age mismatch: Excel={excel_age}, Calculated={calc_age}. Using calculated age.",
                error_code="invalid_value",
                function_name="_fix_age_from_dob"
            )
            ages_fixed += 1

    # Apply fixes:
    # 1. Use calculated age when available and non-negative
    # 2. Use error value for negative ages
    df = df.with_columns(
        pl.when(pl.col("_calc_age").is_not_null())
        .then(
            pl.when(pl.col("_calc_age") < 0)
            .then(pl.lit(settings.error_val_numeric))
            .otherwise(pl.col("_calc_age"))
        )
        .otherwise(pl.col("age"))
        .alias("age")
    )

    # Drop temporary column
    df = df.drop("_calc_age")

    if ages_fixed > 0 or ages_missing > 0 or ages_negative > 0:
        logger.info(
            f"Age fixes applied: {ages_fixed} corrected, {ages_missing} filled from DOB, {ages_negative} negative (set to error)"
        )

    return df


def _validate_dates(df: pl.DataFrame, error_collector: ErrorCollector) -> pl.DataFrame:
    """Validate date columns and replace future dates with error value.

    Dates beyond the tracker year are considered invalid and replaced with
    the error date value (9999-09-09). This matches R pipeline behavior.

    Args:
        df: Input DataFrame with date columns
        error_collector: ErrorCollector for tracking validation errors

    Returns:
        DataFrame with invalid dates replaced
    """
    date_columns = get_date_columns()
    dates_fixed = 0

    # Get the error date as a date type
    error_date = pl.lit(settings.error_val_date).str.to_date()

    for col in date_columns:
        if col not in df.columns:
            continue

        # Skip tracker_date as it's derived and shouldn't be validated
        if col == "tracker_date":
            continue

        # Create a date representing end of tracker year (December 31)
        # Find invalid dates and log them
        temp_df = df.with_columns(
            pl.date(pl.col("tracker_year"), 12, 31).alias("_max_valid_date")
        )

        invalid_dates = temp_df.filter(
            pl.col(col).is_not_null() & (pl.col(col) > pl.col("_max_valid_date"))
        )

        # Log each error
        for row in invalid_dates.iter_rows(named=True):
            patient_id = row.get("patient_id", "UNKNOWN")
            file_name = row.get("file_name", "UNKNOWN")
            original_date = row.get(col)
            tracker_year = row.get("tracker_year")

            logger.warning(
                f"Patient {patient_id}: {col} = {original_date} is beyond tracker year {tracker_year}. "
                f"Replacing with error date."
            )
            error_collector.add_error(
                file_name=file_name,
                patient_id=patient_id,
                column=col,
                original_value=str(original_date),
                error_message=f"Date {original_date} is beyond tracker year {tracker_year}",
                error_code="invalid_value",
                function_name="_validate_dates"
            )
            dates_fixed += 1

        # Replace invalid dates with error date (using inline expression)
        df = temp_df.with_columns(
            pl.when(pl.col(col).is_not_null() & (pl.col(col) > pl.col("_max_valid_date")))
            .then(error_date)
            .otherwise(pl.col(col))
            .alias(col)
        ).drop("_max_valid_date")

    if dates_fixed > 0:
        logger.info(f"Date validation: {dates_fixed} future dates replaced with error value")

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
