"""Patient data cleaning pipeline.

This module orchestrates the complete cleaning pipeline for patient data. The
ordering below is load-bearing, not cosmetic: the meta schema is applied before
type conversion so that unit conversions and derivations can address columns a
given tracker never had, and every derivation runs after the conversion that
produces its inputs and before the validation that bounds its outputs.

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

from a4d.clean.buddhist_era import BUDDHIST_ERA_THRESHOLD, gregorian_from_buddhist
from a4d.clean.converters import (
    correct_decimal_sign,
    cut_numeric_value,
    normalize_excel_formula_errors,
    parse_date_column,
    safe_convert_column,
)
from a4d.clean.glucose import (
    MG_ANALYTICAL_MAX,
    MG_ANALYTICAL_MIN,
    MMOL_ANALYTICAL_MAX,
    MMOL_ANALYTICAL_MIN,
    resolve_glucose_units,
)
from a4d.clean.schema import (
    apply_schema,
    get_date_columns,
    get_patient_data_schema,
)
from a4d.clean.transformers import extract_regimen, strip_string_whitespace
from a4d.clean.validators import validate_all_columns
from a4d.config import settings
from a4d.extract.common import normalize_patient_id_expr
from a4d.findings import report_finding, sheet_context


def clean_patient_data(
    df_raw: pl.DataFrame,
) -> pl.DataFrame:
    """Clean raw patient data following the complete pipeline.

    This function orchestrates all cleaning steps and ensures the output
    conforms to the meta schema, regardless of which columns exist in input.

    Args:
        df_raw: Raw patient data from extraction

    Returns:
        Cleaned DataFrame with complete meta schema applied

    Example:
        >>> from a4d.extract.patient import extract_patient_data
        >>> from a4d.findings import ErrorCollector
        >>>
        >>> collector = ErrorCollector()
        >>> df_raw = extract_patient_data(tracker_file)
        >>> df_clean = clean_patient_data(df_raw, collector)
        >>> # df_clean has ALL schema columns, with consistent types
    """
    logger.info(
        f"Starting patient data cleaning: {len(df_raw)} rows, {len(df_raw.columns)} columns"
    )

    # Step 0: Null out (and log) the source trackers' own formula-error
    # strings, which extraction preserves verbatim (ticket 27). Must run
    # before type conversion so these don't land in safe_convert_column's
    # parse-failure branch and pick up the 999999 sentinel.
    df_raw = normalize_excel_formula_errors(df_raw)

    # Step 0.5: Strip whitespace from the ends of every string cell (ticket
    # 36). End-whitespace never carries meaning in this data, and it runs
    # before validation rather than after because a stray trailing space makes
    # an otherwise-valid value fail allowed-value validation and land on the
    # "Undefined" sentinel: 2019 Kantha Bopha's KH_KB023 has a sex cell reading
    # 'F ', and 72 rows of patient `sex` were being lost that way. Product's
    # cleaning already did this (step 2.16), which left the two arms
    # disagreeing on `file_name` and `sheet_name` for any tracker whose
    # filename or sheet tab carries a stray space -- identifiers that join the
    # arms' tables together.
    df_raw = strip_string_whitespace(df_raw)

    # Step 1: Legacy format fixes
    df = _apply_legacy_fixes(df_raw)

    # Step 2: Pre-processing transformations
    df = _apply_preprocessing(df)

    # Step 3: Data transformations (regimen extraction, lowercasing, etc.)
    df = _apply_transformations(df)

    # Step 4: Apply the meta schema EARLY, so every column exists before the
    # conversions below. Trackers differ in which columns they carry, and the
    # unit conversions and derivations that follow address columns by name --
    # without this they would silently skip whatever a given workbook omitted.
    df = apply_schema(df)

    # Step 5: Type conversions
    df = _apply_type_conversions(df)

    # Step 5.4: Convert Buddhist-era dates to Gregorian (ticket 61).
    # Before _fix_age_from_dob so no age is derived from a BE dob, and before
    # _validate_dates, which would otherwise sentinel every one of them.
    df = _convert_buddhist_era_dates(df)

    # Step 5.5: Derive age from DOB, overriding the sheet's own Age cell --
    # a typed age goes stale between the month it was written and the month
    # the sheet covers, while a date of birth does not (LA_MH060's D.O.B. of
    # 2009-01-16 makes Jan23 an age of 14; the clinic's cell says 13).
    # Must happen after type conversions so DOB is a proper date, and before
    # range validation so the validated age is the derived one.
    df = _fix_age_from_dob(df)

    # Step 5.5b: Fill t1d_diagnosis_age from dob and t1d_diagnosis_date, but
    # only where the tracker recorded no usable age of its own (ticket 52)
    df = _fix_t1d_diagnosis_age(df)

    # Step 5.6: Validate dates (replace future dates with error value)
    # Must happen after type conversions so dates are proper date types
    df = _validate_dates(df)

    # Step 5.7: Resolve glucose readings recorded under the wrong unit's header.
    # Before range validation so the analytical limits judge corrected values,
    # and before step 8 so the mg/mmol cross-derivation sees matching units.
    df = resolve_glucose_units(df)

    # Step 6: Range validation and cleanup
    df = _apply_range_validation(df)

    # Step 7: Allowed values validation
    df = validate_all_columns(df)

    # Step 8: Unit conversions (requires schema to be applied first!)
    df = _apply_unit_conversions(df)

    # Step 9: Create tracker_date from year/month
    df = _add_tracker_date(df)

    # Step 10: Sort by tracker_date and patient_id
    df = df.sort(["tracker_date", "patient_id"])

    logger.info(f"Cleaning complete: {len(df)} rows, {len(df.columns)} columns")

    return df


def _extract_date_from_measurement(df: pl.DataFrame, col_name: str) -> pl.DataFrame:
    """Extract date from measurement values in legacy trackers.

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

    # The closing parenthesis is OPTIONAL, and that is the whole point: 25 of
    # the 30 cells in this population are written `180(May-2017` with no closing
    # bracket at all, near-universal in the 2017/2018 trackers. Requiring it
    # lost the date on every one of them. The prefix is greedy so that a doubled
    # bracket (`196((Dec-2017)`) yields the date after the LAST `(`.
    df = df.with_columns(
        [
            # The greedy prefix leaves a trailing "(" behind on a doubled
            # bracket, which would then fail the numeric cast and lose the
            # reading entirely -- so strip it and keep the 196.
            pl.when(pl.col(col_name).str.contains(r"\(", literal=False))
            .then(
                pl.col(col_name).str.extract(r"^(.*)\(", 1).str.strip_chars().str.strip_chars("(")
            )
            .otherwise(pl.col(col_name))
            .alias(col_name),
            pl.col(col_name).str.extract(r".*\(([^)]*)\)?$", 1).alias(date_col_name),
        ]
    )

    logger.debug(f"Extracted date from {col_name} into {date_col_name}")

    return df


def _apply_legacy_fixes(df: pl.DataFrame) -> pl.DataFrame:
    """Apply fixes for legacy tracker formats (pre-2024).

    Legacy trackers may have:
    - Combined date+value columns (e.g., hba1c_updated contains both)
    - Combined blood pressure values (sys/dias in one column)
    - Different column structures

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with legacy fixes applied
    """
    # Extract dates from measurement columns for pre-2019 trackers. Skipped
    # where the tracker already carries a dedicated *_date column (2019+).
    df = _extract_date_from_measurement(df, "hba1c_updated")
    df = _extract_date_from_measurement(df, "fbg_updated_mg")
    df = _extract_date_from_measurement(df, "fbg_updated_mmol")

    # Split blood pressure for pre-2024 trackers, which record sys/dias in
    # one cell.
    if "blood_pressure_mmhg" in df.columns:
        from a4d.clean.transformers import split_bp_in_sys_and_dias

        df = split_bp_in_sys_and_dias(df)

    return df


def _fix_fbg_column(col: pl.Expr) -> pl.Expr:
    """Fix FBG column text values to numeric equivalents.

    Converts qualitative text to numeric values and removes DKA markers.

    Every pattern here is anchored to the whole cell, deliberately. Matching
    them as substrings turns `Lost follow up` into a glucose of 140 (because
    "fol-low" contains "low") and every `SMBG 50-HI` / `129-HI` into 200,
    discarding the number the clinic actually wrote. A cell that is not
    wholly one of these words is left for numeric parsing or sentinelled.

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
    # Pattern: "MY_SM003_SB" → "MY_SM003" (keep first two underscore-separated parts)
    # Also normalizes hyphens first: "LA-MH093_LF" → "LA_MH093_LF" → "LA_MH093"
    # This ensures consistent patient linking across years when patients transfer clinics
    # Shared with the extraction-side Patient List join key (ticket 58), so the
    # two cannot drift into disagreeing about what one patient's identity is.
    if "patient_id" in df.columns:
        df = df.with_columns(normalize_patient_id_expr(pl.col("patient_id")).alias("patient_id"))

    # Track HbA1c exceeds markers (> or <)
    if "hba1c_baseline" in df.columns:
        df = df.with_columns(
            pl.col("hba1c_baseline")
            .str.contains(r"[><]")
            .fill_null(False)
            .alias("hba1c_baseline_exceeds")
        )
        df = df.with_columns(
            pl.col("hba1c_baseline").str.replace_all(r"[><]", "").alias("hba1c_baseline")
        )

    if "hba1c_updated" in df.columns:
        df = df.with_columns(
            pl.col("hba1c_updated")
            .str.contains(r"[><]")
            .fill_null(False)
            .alias("hba1c_updated_exceeds")
        )
        df = df.with_columns(
            pl.col("hba1c_updated").str.replace_all(r"[><]", "").alias("hba1c_updated")
        )

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

    # Derive insulin_type and insulin_subtype from individual columns (2024+).
    # Values are emitted lowercase here; allowed-value validation canonicalises
    # the case afterwards.
    if "human_insulin_pre_mixed" in df.columns:
        df = _derive_insulin_fields(df)

    return df


_INSULIN_NOT_TICKED = ("", "-", "0", "n", "no")


def _insulin_ticked(column: str) -> pl.Expr:
    """Whether a 2024+ insulin tick box says this subtype applies.

    The template asks for `Y`, but 2024 Sarawak ticks by writing the drug's
    name instead -- `Novorapid` in the rapid-acting column, `Glargine`,
    `Toujeo` or `Ryzodeg` in the long-acting one. Testing for `Y` alone
    discarded those 56 rows' subtypes entirely (ticket 55). The negative
    markers are enumerated instead, because they are the closed set: across all
    248 trackers these five columns hold only `Y`, `-`, `0`, the four drug
    names, and null.
    """
    value = pl.col(column).cast(pl.String).str.strip_chars().str.to_lowercase()
    return pl.col(column).is_not_null() & ~value.is_in(_INSULIN_NOT_TICKED)


def _derive_insulin_fields(df: pl.DataFrame) -> pl.DataFrame:
    """Derive insulin_type and insulin_subtype from individual columns.

    Emits lowercase values; allowed-value validation canonicalises the case
    afterwards.

    For 2024+ trackers:
    - insulin_type: "human insulin" if any human column is Y, else "analog insulin"
    - insulin_subtype: Comma-separated list like "pre-mixed,rapid-acting,long-acting"
      Validation uses allow_csv_subset (see reference_data/validation_rules.yaml) to
      accept each token against allowed_values and rejoin in canonical case.

    A row that ticks no insulin column at all yields None rather than a
    subtype, so a patient with nothing recorded is not reported as having an
    unrecognised regimen.

    Args:
        df: Input DataFrame with individual insulin columns

    Returns:
        DataFrame with insulin_type and insulin_subtype derived
    """
    # Derive insulin_type only when at least one insulin column carries a
    # value: a row where every column is null recorded nothing, and must not
    # be reported as having a type.
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
                _insulin_ticked("human_insulin_pre_mixed")
                | _insulin_ticked("human_insulin_short_acting")
                | _insulin_ticked("human_insulin_intermediate_acting")
            )
            .then(pl.lit("human insulin"))
            .otherwise(pl.lit("analog insulin"))
        )
        .otherwise(None)  # every insulin column null: nothing was recorded
        .alias("insulin_type")
    )

    # Build insulin_subtype as a comma-separated list, lowercase; validation
    # canonicalises the case and checks each token separately (allow_csv_subset
    # in reference_data/validation_rules.yaml).
    df = df.with_columns(
        pl.concat_list(
            [
                pl.when(_insulin_ticked("human_insulin_pre_mixed"))
                .then(pl.lit("pre-mixed"))
                .otherwise(pl.lit(None)),
                pl.when(_insulin_ticked("human_insulin_short_acting"))
                .then(pl.lit("short-acting"))
                .otherwise(pl.lit(None)),
                pl.when(_insulin_ticked("human_insulin_intermediate_acting"))
                .then(pl.lit("intermediate-acting"))
                .otherwise(pl.lit(None)),
                pl.when(_insulin_ticked("analog_insulin_rapid_acting"))
                .then(pl.lit("rapid-acting"))
                .otherwise(pl.lit(None)),
                pl.when(_insulin_ticked("analog_insulin_long_acting"))
                .then(pl.lit("long-acting"))
                .otherwise(pl.lit(None)),
            ]
        )
        .list.drop_nulls()
        .list.join(",")
        # An unticked row deliberately keeps the empty string, which
        # allowed-value validation publishes as "Undefined". That overstates
        # what the clinic recorded -- it ticked nothing, rather than ticking
        # something unrecognised -- and it affects 17,418 rows. Nulling them
        # instead was measured and reverted (ticket 55): it resolved nothing
        # downstream, and whether the consumer distinguishes the two cases has
        # never been established. Left as-is, deliberately, not by oversight.
        .alias("insulin_subtype")
    )

    return df


def _apply_transformations(df: pl.DataFrame) -> pl.DataFrame:
    """Apply data transformations.

    Transformations are explicit Python code (not config-driven):
    - Lowercase status for case-insensitive validation
    - Standardize insulin regimen descriptions
    - Map sex synonyms to M/F
    - Correct European decimal format

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with transformations applied
    """
    # Standardize insulin regimen
    if "insulin_regimen" in df.columns:
        df = extract_regimen(df)

    # Map sex synonyms to M/F
    if "sex" in df.columns:
        from a4d.clean.transformers import fix_sex

        df = fix_sex(df)

    # Fix testing frequency ranges
    if "testing_frequency" in df.columns:
        from a4d.clean.transformers import fix_testing_frequency

        df = fix_testing_frequency(df)

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


def _apply_type_conversions(df: pl.DataFrame) -> pl.DataFrame:
    """Convert columns to target types using safe_convert_column.

    Only converts columns that exist in both the DataFrame and the schema.

    Special handling:
    - Date columns: Use flexible date parser (handles Mar-18, Excel serials, etc.)
    - Integer columns: Convert via Float64 first to handle decimals

    Args:
        df: Input DataFrame

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
            # Strip a trailing time component if present
            # (e.g., "2009-04-17 00:00:00" → "2009-04-17"). Matches the time
            # itself rather than splitting on the first space: a date can
            # legitimately contain one ("Jun 2006", ticket 37), and taking the
            # first token dropped the year and left a month name the parser
            # then completed from the current date.
            df = df.with_columns(
                pl.col(col)
                .cast(pl.Utf8)
                .str.replace(r"\s+\d{1,2}:\d{2}(:\d{2})?(\.\d+)?$", "")
                .alias(col)
            )
            # Use custom date parser for flexibility (handles Mar-18, Excel serials, etc.)
            df = parse_date_column(df, col)
        # Special handling for Int32: convert via Float64 first (handles "14.0" → 14.0 → 14)
        elif target_type == pl.Int32:
            df = safe_convert_column(df, col, pl.Float64)
            df = df.with_columns(pl.col(col).round(0).cast(pl.Int32, strict=False).alias(col))
        else:
            df = safe_convert_column(
                df=df,
                column=col,
                target_type=target_type,
            )

    return df


def _calculate_bmi(df: pl.DataFrame) -> pl.DataFrame:
    """Calculate BMI from weight and height.

    REPLACES any existing BMI value with weight / height^2, because a typed
    BMI goes stale as the patient's weight changes while the two measurements
    it derives from are re-recorded each month.

    Must be called after height and weight have been range-validated and before
    the BMI bound is applied. Deriving it first produced a BMI that passed its
    own bound while resting on an impossible height: 60 / 2.43^2 = 10.16, from
    a height cell that should have been rejected outright.

    Args:
        df: Input DataFrame

    Returns:
        DataFrame with calculated BMI column
    """
    from a4d.clean.transformers import fix_bmi

    return fix_bmi(df)


def _apply_range_validation(df: pl.DataFrame) -> pl.DataFrame:
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

    Returns:
        DataFrame with range validation applied
    """
    # Height: convert cm to m only above 50. A value between 2.3 and 50 is
    # neither unit, and dividing it by 100 turns an unusable cell into a
    # plausible-looking metre reading. The threshold was 2.3 and 120 source
    # cells reading 2.43, 6.9 and 13.0 were being published as 0.069 metres
    # (ticket 55); they are now rejected instead.
    if "height" in df.columns:
        df = df.with_columns(
            pl.when(pl.col("height") > 50)
            .then(pl.col("height") / 100.0)
            .otherwise(pl.col("height"))
            .alias("height")
        )
        df = cut_numeric_value(df, "height", 0, 2.3)

    # Weight: 0-200 kg
    if "weight" in df.columns:
        df = cut_numeric_value(df, "weight", 0, 200)

    # BMI is derived here rather than earlier so it sees the validated height:
    # an out-of-bounds height voids the BMI instead of producing one
    # from an impossible measurement.
    df = _calculate_bmi(df)

    # BMI: 4-60
    if "bmi" in df.columns:
        df = cut_numeric_value(df, "bmi", 10, 80)

    # Age: 0-25 years
    if "age" in df.columns:
        df = cut_numeric_value(df, "age", 0, 100)

    # HbA1c baseline: 4-18%
    if "hba1c_baseline" in df.columns:
        df = cut_numeric_value(df, "hba1c_baseline", 0, 25)

    # HbA1c updated: 4-18%
    if "hba1c_updated" in df.columns:
        df = cut_numeric_value(df, "hba1c_updated", 0, 25)

    # FBG: the analytical limits of the machines in use, given by A4D's medical
    # advisor 2026-08-17 (ticket 42). The permissive end of each range he gave is
    # used, so only a reading no machine could have produced is rejected. This
    # replaces an inherited 0-150 mmol/L bound that was more than three times
    # his ceiling, and covers the three columns that carried no bound at all.
    # 832 readings are rejected on these limits.
    for column in ("fbg_baseline_mg", "fbg_updated_mg"):
        if column in df.columns:
            df = cut_numeric_value(df, column, MG_ANALYTICAL_MIN, MG_ANALYTICAL_MAX)
    for column in ("fbg_baseline_mmol", "fbg_updated_mmol"):
        if column in df.columns:
            df = cut_numeric_value(df, column, MMOL_ANALYTICAL_MIN, MMOL_ANALYTICAL_MAX)

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


def _fix_age_from_dob(df: pl.DataFrame) -> pl.DataFrame:
    """Fix age by calculating from DOB and tracker date.

    Always uses the age calculated from DOB rather than the sheet's own Age
    cell. A typed age is correct only for the month someone typed it; the
    date of birth stays correct. LA_MH060's recovered D.O.B. of 2009-01-16
    makes Jan23 an age of 14, where the workbook's own cell still reads 13.

    Logic:
    1. Calculate age: tracker_year - birth_year
    2. Adjust if birthday hasn't occurred yet: if tracker_month < birth_month: age -= 1
    3. If calculated age differs from Excel age, log warning and use calculated
    4. If calculated age is negative, use error value and log warning

    Args:
        df: DataFrame with age, dob, tracker_year, tracker_month, patient_id columns

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

    logger.info("Deriving age from DOB")

    error_date = pl.lit(settings.error_val_date).str.to_date()

    # Only calculate if dob is valid (not null, not error date)
    valid_dob = pl.col("dob").is_not_null() & (pl.col("dob") != error_date)

    # Calculate age from DOB
    # calc_age = tracker_year - year(dob)
    # if tracker_month < month(dob): calc_age -= 1
    df = df.with_columns(
        pl.when(valid_dob)
        .then(
            pl.col("tracker_year")
            - pl.col("dob").dt.year()
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
        excel_age = row["age"]
        calc_age = row["_calc_age"]

        # One finding per event, naming the patient and the column. An earlier
        # stage-level copy carrying only the message was dropped: it said the
        # same thing without the two fields that let a reader find the cell.
        #
        # The negative check comes first because a date of birth after the
        # visit is a workbook defect either way. Testing the empty-age branch
        # first published "Age missing, calculated from DOB as -1" as a
        # recovery -- the age cell being blank says nothing about whether the
        # date of birth it was derived from is sound.
        if calc_age < 0:
            report_finding(
                patient_id=patient_id,
                column="age",
                original_value="NULL" if excel_age is None else str(excel_age),
                message=f"Calculated age is negative ({calc_age}), check DOB",
                error_code="age_negative_from_dob",
                **sheet_context(row),
                function_name="_fix_age_from_dob",
            )
            ages_negative += 1
        elif excel_age is None or (excel_age == settings.error_val_numeric):
            report_finding(
                patient_id=patient_id,
                column="age",
                original_value=excel_age if excel_age is not None else "NULL",
                message=f"Age missing, calculated from DOB as {calc_age}",
                error_code="age_derived_from_dob",
                **sheet_context(row),
                function_name="_fix_age_from_dob",
            )
            ages_missing += 1
        else:
            report_finding(
                patient_id=patient_id,
                column="age",
                original_value=str(excel_age),
                message=(
                    f"Age mismatch: Excel={excel_age}, Calculated={calc_age}. Using calculated age."
                ),
                error_code="age_corrected_from_dob",
                **sheet_context(row),
                function_name="_fix_age_from_dob",
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
            f"Age fixes applied: {ages_fixed} corrected, "
            f"{ages_missing} filled from DOB, "
            f"{ages_negative} negative (set to error)"
        )

    return df


def _fix_t1d_diagnosis_age(df: pl.DataFrame) -> pl.DataFrame:
    """Fill t1d_diagnosis_age from dob and t1d_diagnosis_date, but only when
    the tracker's own recorded value is missing or an Excel error sentinel.

    A directly recorded diagnosis age is a real clinic-entered value, not
    something to discard in favour of date arithmetic. An earlier version
    overwrote it whenever both dates parsed, which threw the recorded value
    away entirely when a date failed to parse (falling to null) and silently
    shifted it by +/-1 when it parsed but disagreed with the tracker's figure.
    Deriving only into the gap keeps both: MM_MD010's cell reads `11yr`, which
    no arithmetic is needed to read, while a patient with a blank cell and two
    good dates still gets an age.

    "Missing" includes the 999999 sentinel, since a cell that failed numeric
    conversion recorded no usable age either.

    Args:
        df: DataFrame with dob, t1d_diagnosis_date, t1d_diagnosis_age columns

    Returns:
        DataFrame with t1d_diagnosis_age filled from dates where missing
    """
    required_cols = ["dob", "t1d_diagnosis_date", "t1d_diagnosis_age"]
    if not all(col in df.columns for col in required_cols):
        return df

    error_date = pl.lit(settings.error_val_date).str.to_date()

    # Only calculate if both dates are valid (not null, not error date)
    valid_dob = pl.col("dob").is_not_null() & (pl.col("dob") != error_date)
    valid_diagnosis = pl.col("t1d_diagnosis_date").is_not_null() & (
        pl.col("t1d_diagnosis_date") != error_date
    )
    # Keep the raw recorded age unless it's missing or an Excel error sentinel
    has_recorded_age = pl.col("t1d_diagnosis_age").is_not_null() & (
        pl.col("t1d_diagnosis_age") != settings.error_val_numeric
    )

    # Calculate age at diagnosis: year(diagnosis_date) - year(dob)
    # Adjust if birthday hasn't occurred yet in diagnosis year
    calculated_age = (
        pl.col("t1d_diagnosis_date").dt.year()
        - pl.col("dob").dt.year()
        - pl.when(pl.col("t1d_diagnosis_date").dt.month() < pl.col("dob").dt.month())
        .then(1)
        .otherwise(0)
    )

    # A diagnosis recorded before the patient was born is a workbook defect,
    # and it is reported whether or not the age cell was filled in -- the two
    # dates contradict each other either way. Emitted before the calculation
    # below, which has nothing to say about such a row and publishes null
    # (ticket 52); a recorded age is left standing, because 3, 9 or 14 is a
    # plausible clinic-entered number and the suspect evidence is the date
    # pair, not the age. 8 patients across 7 trackers, 58 rows (ticket 73).
    contradiction = valid_dob & valid_diagnosis & (calculated_age < 0)
    for patient_id, dob, diagnosis_date, recorded_age in (
        df.filter(contradiction)
        .select("patient_id", "dob", "t1d_diagnosis_date", "t1d_diagnosis_age")
        .unique(subset=["patient_id", "dob", "t1d_diagnosis_date"], maintain_order=True)
        .iter_rows()
    ):
        report_finding(
            patient_id=patient_id or "unknown",
            column="t1d_diagnosis_age",
            original_value="NULL" if recorded_age is None else str(recorded_age),
            message=(
                f"Diagnosis date {diagnosis_date} precedes date of birth {dob}, "
                f"so the age at diagnosis cannot be calculated"
            ),
            error_code="diagnosis_age_negative_from_dob",
            function_name="_fix_t1d_diagnosis_age",
        )

    df = df.with_columns(
        pl.when(has_recorded_age)
        .then(pl.col("t1d_diagnosis_age"))
        .when(valid_dob & valid_diagnosis)
        .then(pl.when(calculated_age >= 0).then(calculated_age).otherwise(None))
        .otherwise(None)
        .cast(pl.Int32)
        .alias("t1d_diagnosis_age")
    )

    return df


def _convert_buddhist_era_dates(df: pl.DataFrame) -> pl.DataFrame:
    """Shift Buddhist-era dates to Gregorian before anything else reads them.

    Thai clinics keep their trackers in a Thai-locale Excel, so a date arrives
    with a Buddhist-era year (BE = CE + 543) -- the calendar the clinic uses,
    not an error it made. Without this step ``_validate_dates`` sees a year
    centuries ahead and clobbers the cell with the 9999-09-09 sentinel, so the
    reading is destroyed rather than merely published oddly: 381 cells across
    95 distinct values in the 254-tracker corpus (ticket 61). 2022 Hat Yai's
    2560-01-01 converts to the 2017-01-01 that the same patient's D.O.B. and
    recruitment date independently give, which is the check that established
    the shift is a recovery rather than a rewrite.

    A cell converts when its year is at or beyond ``BUDDHIST_ERA_THRESHOLD``
    and the shifted year is no later than the tracker's own year. There is no
    lower bound, unlike the product arm's band: a diagnosis or screening date
    legitimately predates its tracker by decades, and the upper bound alone
    already rejects what does not decode (``3035`` -> 2492, ``5025`` -> 4482),
    leaving those to be sentinelled and reported as source defects.

    Runs before ``_fix_age_from_dob`` so an age is never derived from a BE
    ``dob``. Cleaned stage only -- the raw stage keeps what the workbook says.
    """
    converting = [c for c in get_date_columns() if c in df.columns and c != "tracker_date"]
    converted_cells = 0

    for col in converting:
        shifted = gregorian_from_buddhist(col)
        mask = (
            pl.col(col).is_not_null()
            & (pl.col(col).dt.year() >= BUDDHIST_ERA_THRESHOLD)
            & shifted.is_not_null()
            & (shifted <= pl.date(pl.col("tracker_year"), 12, 31))
        )

        candidates = df.with_columns(shifted.alias("_shifted")).filter(mask)
        for patient_id, original, shifted_value, sheet_name, tracker_month in candidates.select(
            "patient_id", col, "_shifted", "sheet_name", "tracker_month"
        ).iter_rows():
            report_finding(
                patient_id=patient_id or "UNKNOWN",
                column=col,
                original_value=str(original),
                message=(f"Date {original} is a Buddhist-era year; converted to {shifted_value}"),
                error_code="buddhist_era_converted",
                sheet_name=sheet_name or "",
                tracker_month=tracker_month,
                function_name="_convert_buddhist_era_dates",
            )
            converted_cells += 1

        df = df.with_columns(pl.when(mask).then(shifted).otherwise(pl.col(col)).alias(col))

    if converted_cells > 0:
        logger.info(f"Buddhist-era conversion: {converted_cells} dates shifted to Gregorian")

    return df


def _validate_dates(df: pl.DataFrame) -> pl.DataFrame:
    """Validate date columns and replace future dates with error value.

    Dates beyond the tracker year are considered invalid and replaced with
    the error date value (9999-09-09).

    A date after the tracker's own year cannot be a record of something that
    happened during it. The population is a real source defect rather than a
    parsing artifact: 2022 Vietnam National Children's Hospital records every
    diagnosis date as a 2023 one, for patients recruited in 2017 (ticket 51,
    722 cells). Sentinelling marks the value unusable rather than inventing a
    plausible one; the workbook is what needs correcting, which is why each
    rejection is also logged per patient.

    Args:
        df: Input DataFrame with date columns

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
        temp_df = df.with_columns(pl.date(pl.col("tracker_year"), 12, 31).alias("_max_valid_date"))

        invalid_dates = temp_df.filter(
            pl.col(col).is_not_null() & (pl.col(col) > pl.col("_max_valid_date"))
        )

        # Log each error (tuple-unpack avoids per-row dict construction)
        for (
            patient_id,
            file_name,
            original_date,
            tracker_year,
            sheet_name,
            tracker_month,
        ) in invalid_dates.select(
            "patient_id", "file_name", col, "tracker_year", "sheet_name", "tracker_month"
        ).iter_rows():
            patient_id = patient_id if patient_id is not None else "UNKNOWN"
            file_name = file_name if file_name is not None else "UNKNOWN"

            report_finding(
                patient_id=patient_id,
                column=col,
                original_value=str(original_date),
                message=f"Date {original_date} is beyond tracker year {tracker_year}",
                error_code="date_beyond_tracker_year",
                sheet_name=sheet_name or "",
                tracker_month=tracker_month,
                function_name="_validate_dates",
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
            pl.concat_str(
                [
                    pl.col("tracker_year").cast(pl.String),
                    pl.lit("-"),
                    pl.col("tracker_month").cast(pl.String),
                    pl.lit("-01"),
                ]
            )
            .str.to_date("%Y-%m-%d")
            .alias("tracker_date")
        )

    return df


def clean_patient_file(
    raw_parquet_path: Path,
    output_parquet_path: Path,
) -> None:
    """Clean a single patient data parquet file.

    This is the main entry point for cleaning a tracker file.

    Args:
        raw_parquet_path: Path to raw patient parquet (from extraction)
        output_parquet_path: Path to write cleaned parquet

    Example:
        >>> from pathlib import Path
        >>> raw_path = Path("output/patient_data_raw/2024_Hospital_patient_raw.parquet")
        >>> clean_path = Path("output/patient_data_clean/2024_Hospital_patient_clean.parquet")
        >>> clean_patient_file(raw_path, clean_path)
    """
    logger.info(f"Cleaning patient file: {raw_parquet_path}")

    # Read raw parquet
    df_raw = pl.read_parquet(raw_parquet_path)

    # Clean data
    df_clean = clean_patient_data(df_raw)

    # Create output directory if needed
    output_parquet_path.parent.mkdir(parents=True, exist_ok=True)

    # Write cleaned parquet
    df_clean.write_parquet(output_parquet_path)

    logger.info(f"Cleaned patient file written: {output_parquet_path}")
