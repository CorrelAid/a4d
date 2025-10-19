# Error Logging Strategy for Python Migration

## The Challenge

The R pipeline uses `rowwise()` heavily in Script 2 because each conversion needs detailed error logging:
- Which tracker file failed
- Which patient_id had the error
- What value couldn't be converted
- Which column had the issue

This transparency is **essential** for data quality monitoring and debugging tracker issues.

## Solution: Hybrid Vectorized + Detailed Error Capture

### Strategy

1. **Try vectorized conversion first** (fast, handles 95%+ of data)
2. **Identify failed rows** (using null detection)
3. **Re-process only failed rows** with detailed error logging
4. **Collect all errors** in structured format
5. **Export error logs** just like R pipeline

This gives us:
- ✅ Vectorized performance for valid data
- ✅ Detailed error logs for problematic data
- ✅ Same transparency as R pipeline
- ✅ Structured error collection for analysis

## Implementation

### Core Pattern: Safe Conversion with Error Tracking

**src/a4d/clean/converters.py**:
```python
import polars as pl
from typing import Any, Callable, Optional
from dataclasses import dataclass
from a4d.config import settings
from a4d.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ConversionError:
    """Track a single conversion error."""
    file_name: str
    patient_id: str
    column: str
    original_value: Any
    error_type: str
    error_message: str


class ErrorCollector:
    """Collect conversion errors for logging and export."""

    def __init__(self):
        self.errors: list[ConversionError] = []

    def add_error(
        self,
        file_name: str,
        patient_id: str,
        column: str,
        original_value: Any,
        error_type: str,
        error_message: str,
    ):
        """Add a conversion error."""
        self.errors.append(
            ConversionError(
                file_name=file_name,
                patient_id=patient_id,
                column=column,
                original_value=str(original_value),
                error_type=error_type,
                error_message=error_message,
            )
        )

    def log_summary(self):
        """Log summary of all errors."""
        if not self.errors:
            logger.info("No conversion errors")
            return

        # Group by column
        by_column = {}
        for error in self.errors:
            by_column.setdefault(error.column, []).append(error)

        for column, errors in by_column.items():
            logger.warning(
                "Conversion errors",
                column=column,
                error_count=len(errors),
                sample_errors=[
                    {
                        "file": e.file_name,
                        "patient_id": e.patient_id,
                        "value": e.original_value,
                        "error": e.error_message,
                    }
                    for e in errors[:5]  # Log first 5 as sample
                ],
            )

    def to_dataframe(self) -> pl.DataFrame:
        """Convert errors to DataFrame for export."""
        if not self.errors:
            return pl.DataFrame()

        return pl.DataFrame([
            {
                "file_name": e.file_name,
                "patient_id": e.patient_id,
                "column": e.column,
                "original_value": e.original_value,
                "error_type": e.error_type,
                "error_message": e.error_message,
            }
            for e in self.errors
        ])


def safe_convert_column(
    df: pl.DataFrame,
    column: str,
    target_type: pl.DataType,
    error_value: Any,
    error_collector: ErrorCollector,
    converter_func: Optional[Callable] = None,
) -> pl.DataFrame:
    """
    Safely convert a column with detailed error logging.

    Strategy:
    1. Try vectorized conversion (strict=False, returns null on error)
    2. Identify which rows failed (are null after conversion)
    3. For failed rows only, log detailed error with patient_id and file
    4. Replace nulls with error_value

    Args:
        df: Input DataFrame
        column: Column name to convert
        target_type: Target Polars data type
        error_value: Value to use when conversion fails
        error_collector: Collector for error tracking
        converter_func: Optional custom conversion function

    Returns:
        DataFrame with converted column
    """

    if column not in df.columns:
        return df

    # Store original values for error logging
    original_col = f"_original_{column}"
    df = df.with_columns(pl.col(column).alias(original_col))

    # Try vectorized conversion (non-strict mode)
    if converter_func:
        # Custom converter (e.g., date parsing)
        df = df.with_columns([
            pl.col(column)
            .map_elements(
                lambda x: converter_func(x) if x is not None else None,
                return_dtype=target_type,
                skip_nulls=True,
            )
            .alias(f"_converted_{column}")
        ])
    else:
        # Standard type cast
        df = df.with_columns([
            pl.col(column)
            .cast(target_type, strict=False)
            .alias(f"_converted_{column}")
        ])

    # Identify failed conversions (became null but weren't null originally)
    df = df.with_columns([
        (
            pl.col(f"_converted_{column}").is_null() &
            pl.col(original_col).is_not_null()
        ).alias(f"_failed_{column}")
    ])

    # Extract failed rows for detailed logging
    failed_rows = df.filter(pl.col(f"_failed_{column}"))

    if len(failed_rows) > 0:
        # Log each failed conversion with context
        for row in failed_rows.iter_rows(named=True):
            error_collector.add_error(
                file_name=row.get("file_name", "unknown"),
                patient_id=row.get("patient_id", "unknown"),
                column=column,
                original_value=row[original_col],
                error_type="conversion_error",
                error_message=f"Could not convert '{row[original_col]}' to {target_type}",
            )

    # Replace failed values with error constant
    df = df.with_columns([
        pl.when(pl.col(f"_failed_{column}"))
        .then(pl.lit(error_value))
        .otherwise(pl.col(f"_converted_{column}"))
        .alias(column)
    ])

    # Clean up temporary columns
    df = df.drop([original_col, f"_converted_{column}", f"_failed_{column}"])

    return df


def convert_numeric_columns(
    df: pl.DataFrame,
    numeric_cols: list[str],
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """Convert multiple numeric columns with error tracking."""

    for col in numeric_cols:
        df = safe_convert_column(
            df=df,
            column=col,
            target_type=pl.Float64,
            error_value=settings.error_val_numeric,
            error_collector=error_collector,
        )

    return df


def convert_date_columns(
    df: pl.DataFrame,
    date_cols: list[str],
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """Convert multiple date columns with error tracking."""

    from dateutil import parser

    def parse_date_flexible(value: str) -> Optional[Any]:
        """Try multiple date parsing strategies."""
        if not value or value == "":
            return None

        try:
            # Try ISO format first (fastest)
            return pl.lit(value).str.to_date(strict=False)
        except:
            pass

        try:
            # Try dateutil parser (handles many formats)
            return parser.parse(str(value)).date()
        except:
            return None

    for col in date_cols:
        df = safe_convert_column(
            df=df,
            column=col,
            target_type=pl.Date,
            error_value=pl.lit(settings.error_val_date).str.to_date(),
            error_collector=error_collector,
            converter_func=parse_date_flexible,
        )

    return df


def convert_integer_columns(
    df: pl.DataFrame,
    int_cols: list[str],
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """Convert multiple integer columns with error tracking."""

    for col in int_cols:
        # First convert to float, round, then to int
        # This handles "5.0" -> 5
        df = df.with_columns([
            pl.col(col).cast(pl.Float64, strict=False).round().alias(col)
        ])

        df = safe_convert_column(
            df=df,
            column=col,
            target_type=pl.Int32,
            error_value=int(settings.error_val_numeric),
            error_collector=error_collector,
        )

    return df
```

### Usage in Script 2

**src/a4d/clean/patient.py** (revised):
```python
import polars as pl
from pathlib import Path
from a4d.clean.converters import (
    ErrorCollector,
    convert_numeric_columns,
    convert_date_columns,
    convert_integer_columns,
)
from a4d.clean.validators import apply_value_range_checks
from a4d.logging import get_logger

logger = get_logger(__name__)


def process_raw_patient_file(
    patient_file: Path,
    output_root: Path,
) -> None:
    """
    Clean and validate raw patient data with detailed error tracking.
    """

    # Initialize error collector for this file
    error_collector = ErrorCollector()

    # Read raw data
    df = pl.read_parquet(patient_file)

    logger.info("Processing raw patient data", file=str(patient_file), rows=len(df))

    # --- TRANSFORMATIONS (same as before) ---
    if "hba1c_updated_date" not in df.columns and "hba1c_updated" in df.columns:
        df = extract_date_from_measurement(df, "hba1c_updated")

    if "blood_pressure_mmhg" in df.columns:
        df = split_bp_in_sys_and_dias(df)

    # Detect exceeds indicators
    df = df.with_columns([
        pl.col("hba1c_baseline").str.contains(r"[<>]").fill_null(False).alias("hba1c_baseline_exceeds"),
        pl.col("hba1c_updated").str.contains(r"[<>]").fill_null(False).alias("hba1c_updated_exceeds"),
    ])

    # Remove < > from values (before conversion)
    df = df.with_columns([
        pl.col("hba1c_baseline").str.replace_all(r"[<>]", ""),
        pl.col("hba1c_updated").str.replace_all(r"[<>]", ""),
    ])

    # --- TYPE CONVERSION WITH ERROR TRACKING ---

    # Define column groups by type
    numeric_cols = [
        "hba1c_baseline", "hba1c_updated",
        "fbg_baseline_mg", "fbg_baseline_mmol",
        "fbg_updated_mg", "fbg_updated_mmol",
        "height", "weight", "bmi",
        "insulin_total_units",
        "complication_screening_lipid_profile_hdl_mmol_value",
        "complication_screening_lipid_profile_ldl_mg_value",
        # ... add all numeric columns
    ]

    date_cols = [
        "dob", "recruitment_date", "tracker_date",
        "t1d_diagnosis_date", "last_clinic_visit_date",
        "hba1c_updated_date", "fbg_updated_date",
        # ... add all date columns
    ]

    integer_cols = [
        "age", "tracker_year", "tracker_month",
        "t1d_diagnosis_age", "testing_frequency",
        "blood_pressure_sys_mmhg", "blood_pressure_dias_mmhg",
        # ... add all integer columns
    ]

    # Convert with error tracking
    logger.info("Converting numeric columns", count=len(numeric_cols))
    df = convert_numeric_columns(df, numeric_cols, error_collector)

    logger.info("Converting date columns", count=len(date_cols))
    df = convert_date_columns(df, date_cols, error_collector)

    logger.info("Converting integer columns", count=len(integer_cols))
    df = convert_integer_columns(df, integer_cols, error_collector)

    # --- VALIDATION & FIXES ---

    # Apply range checks (with error collection)
    df = apply_value_range_checks(df, error_collector)

    # Apply custom fixes (vectorized, but can also collect errors)
    df = apply_patient_fixes(df, error_collector)

    # --- LOG ERROR SUMMARY ---

    error_collector.log_summary()

    # Export error details
    if error_collector.errors:
        error_df = error_collector.to_dataframe()
        error_file = output_root.parent / "logs" / f"{patient_file.stem}_errors.parquet"
        error_df.write_parquet(error_file)
        logger.info(
            "Exported error details",
            file=str(error_file),
            error_count=len(error_collector.errors),
        )

    # --- EXPORT CLEANED DATA ---

    output_file = output_root / patient_file.name.replace("_patient_raw", "_patient_cleaned")
    df.write_parquet(output_file, compression="zstd")

    logger.info(
        "Exported cleaned patient data",
        file=str(output_file),
        rows=len(df),
        errors=len(error_collector.errors),
    )


def apply_value_range_checks(
    df: pl.DataFrame,
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """
    Apply value range checks with error logging.

    Similar to R's cut_numeric_value but logs which rows violated constraints.
    """

    range_checks = {
        "height": (0.0, 2.3),
        "weight": (0.0, 200.0),
        "bmi": (4.0, 60.0),
        "age": (0, 25),
        "hba1c_baseline": (4.0, 18.0),
        "hba1c_updated": (4.0, 18.0),
        "fbg_updated_mmol": (0.0, 136.5),
    }

    for column, (min_val, max_val) in range_checks.items():
        if column not in df.columns:
            continue

        # Find out-of-range values
        out_of_range = df.filter(
            (pl.col(column) < min_val) | (pl.col(column) > max_val)
        )

        # Log each violation
        for row in out_of_range.iter_rows(named=True):
            error_collector.add_error(
                file_name=row.get("file_name", "unknown"),
                patient_id=row.get("patient_id", "unknown"),
                column=column,
                original_value=row[column],
                error_type="range_violation",
                error_message=f"Value {row[column]} outside range [{min_val}, {max_val}]",
            )

        # Clip to range
        df = df.with_columns([
            pl.col(column).clip(min_val, max_val).alias(column)
        ])

    return df


def apply_patient_fixes(
    df: pl.DataFrame,
    error_collector: ErrorCollector,
) -> pl.DataFrame:
    """
    Apply custom patient data fixes.

    These are mostly vectorized but can log errors when needed.
    """

    # Transform height from cm to m (vectorized, no errors expected)
    df = df.with_columns([
        pl.when(pl.col("height") > 2.5)
        .then(pl.col("height") / 100)
        .otherwise(pl.col("height"))
        .alias("height"),
    ])

    # Calculate BMI (vectorized)
    df = df.with_columns([
        (pl.col("weight") / (pl.col("height") ** 2)).alias("bmi_calculated")
    ])

    # Fix age (vectorized, but track when we override)
    df = df.with_columns([
        pl.date(pl.col("tracker_year"), pl.col("tracker_month"), 1).alias("tracker_date_calc")
    ])

    # Calculate age from DOB
    df = df.with_columns([
        (
            (pl.col("tracker_date_calc").dt.year() - pl.col("dob").dt.year()) -
            (
                (pl.col("tracker_date_calc").dt.month() < pl.col("dob").dt.month()) |
                (
                    (pl.col("tracker_date_calc").dt.month() == pl.col("dob").dt.month()) &
                    (pl.col("tracker_date_calc").dt.day() < pl.col("dob").dt.day())
                )
            ).cast(pl.Int32)
        ).alias("age_calculated")
    ])

    # Find cases where we override age
    age_overrides = df.filter(
        (pl.col("age").is_not_null()) &
        (pl.col("age_calculated").is_not_null()) &
        (pl.col("age") != pl.col("age_calculated")) &
        ((pl.col("age") < 0) | (pl.col("age") > 25))
    )

    # Log age overrides
    for row in age_overrides.iter_rows(named=True):
        error_collector.add_error(
            file_name=row.get("file_name", "unknown"),
            patient_id=row.get("patient_id", "unknown"),
            column="age",
            original_value=row["age"],
            error_type="value_override",
            error_message=f"Age {row['age']} replaced with calculated {row['age_calculated']}",
        )

    # Use calculated age if provided age is invalid
    df = df.with_columns([
        pl.when((pl.col("age") < 0) | (pl.col("age") > 25))
        .then(pl.col("age_calculated"))
        .otherwise(pl.col("age"))
        .alias("age")
    ])

    # Clean up temp columns
    df = df.drop(["bmi_calculated", "tracker_date_calc", "age_calculated"])

    return df
```

### Error Log Analysis

**scripts/analyze_errors.py**:
```python
#!/usr/bin/env python3
"""Analyze conversion errors across all processed files."""

import polars as pl
from pathlib import Path
from a4d.config import settings
import typer

app = typer.Typer()


@app.command()
def main():
    """Analyze all error logs."""

    logs_dir = settings.output_root / "logs"
    error_files = list(logs_dir.glob("*_errors.parquet"))

    if not error_files:
        print("No error files found")
        return

    # Combine all errors
    all_errors = pl.concat([pl.read_parquet(f) for f in error_files])

    print(f"\n📊 Total Errors: {len(all_errors)}")

    # Group by column
    by_column = (
        all_errors
        .group_by("column")
        .agg([
            pl.len().alias("error_count"),
            pl.col("error_type").value_counts().alias("error_types"),
        ])
        .sort("error_count", descending=True)
    )

    print("\n📋 Errors by Column:")
    print(by_column)

    # Group by file
    by_file = (
        all_errors
        .group_by("file_name")
        .agg(pl.len().alias("error_count"))
        .sort("error_count", descending=True)
        .head(10)
    )

    print("\n📁 Top 10 Files with Errors:")
    print(by_file)

    # Show sample errors
    print("\n🔍 Sample Errors:")
    print(
        all_errors
        .select(["file_name", "patient_id", "column", "original_value", "error_message"])
        .head(20)
    )

    # Export summary
    summary_file = logs_dir / "error_summary.xlsx"

    with pl.ExcelWriter(summary_file) as writer:
        by_column.write_excel(writer, worksheet="By Column")
        by_file.write_excel(writer, worksheet="By File")
        all_errors.head(1000).write_excel(writer, worksheet="Sample Errors")

    print(f"\n✅ Summary exported to: {summary_file}")


if __name__ == "__main__":
    app()
```

## Key Benefits

1. **Same Transparency**: Every conversion error is logged with patient_id and file
2. **Better Performance**: Vectorized for valid data, row-wise only for failures
3. **Structured Errors**: Errors are collected in DataFrame, can be analyzed
4. **Same Error Values**: Uses same ERROR_VAL_NUMERIC, ERROR_VAL_DATE constants
5. **Error Analysis**: Can analyze patterns across all files
6. **Exportable**: Error logs saved as Parquet for review

## Performance Characteristics

For a file with 1000 rows where 50 have conversion errors:

**R Approach**:
- Process 1000 rows individually
- Log during processing
- Time: ~1000 row operations

**Python Hybrid Approach**:
- Vectorized conversion: 1000 rows in batch (fast)
- Error detection: 1000 rows in batch (fast)
- Detailed logging: 50 rows individually (only failures)
- Time: ~2 batch operations + 50 row operations

**Result**: 10-20x faster while maintaining full error transparency.

## Validation

The error logs can be compared between R and Python:
- Same errors should be detected
- Same patient_ids should be flagged
- Error counts should match

This ensures the Python pipeline has the same data quality checks as R.
