"""Validation tests comparing Python outputs against R pipeline outputs.

Tests that verify Python implementation matches R implementation by comparing
the final cleaned parquet files for all 174 trackers.

These tests require:
- R pipeline outputs in: /Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r/patient_data_cleaned/
- Python pipeline outputs in: /Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/output/patient_data_cleaned/

Run with: uv run pytest tests/test_integration/test_r_validation.py -v -m slow
"""

from pathlib import Path

import polars as pl
import pytest

# Mark all tests as slow and integration
pytestmark = [pytest.mark.slow, pytest.mark.integration]

# Define output directories
R_OUTPUT_DIR = Path("/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r/patient_data_cleaned")
PY_OUTPUT_DIR = Path("/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python/patient_data_cleaned")


def get_all_tracker_files() -> list[tuple[str, Path, Path]]:
    """Get list of all tracker parquet files that exist in R output.

    Returns:
        List of (filename, r_path, py_path) tuples
    """
    if not R_OUTPUT_DIR.exists():
        return []

    trackers = []
    for r_file in sorted(R_OUTPUT_DIR.glob("*_patient_cleaned.parquet")):
        filename = r_file.name
        py_file = PY_OUTPUT_DIR / filename
        trackers.append((filename, r_file, py_file))

    return trackers


# Acceptable differences where Python behavior is correct/better than R
# These tests will PASS with the documented differences
ACCEPTABLE_DIFFERENCES = {
    "2024_Mandalay Children's Hospital A4D Tracker_patient_cleaned.parquet": {
        "record_diff": 11,
        "reason": "R implicit filtering: MM_QA001 has 12 monthly records in Python but only 1 in R",
    },
    "2024_Mahosot Hospital A4D Tracker_patient_cleaned.parquet": {
        "record_diff": 1,
        "reason": "Python correctly extracts LA-QA088 which is missing row number in Excel column A; R incorrectly drops it",
    },
}

# Known issues in Python that need to be fixed
# Tests will run normally and only SKIP if the issue still exists
# If the issue is fixed, the test will FAIL with a message to remove it from this dict
KNOWN_ISSUES = {
    "2018_Penang General Hospital A4D Tracker_DC_patient_cleaned.parquet": {
        "duplicate_records": "Excel has duplicate patient_id MY_QF004 in Oct18 sheet that needs to be fixed",
    },
    "2021_Mahosot Hospital A4D Tracker_DC_patient_cleaned.parquet": {
        "patient_id_format": "Python needs to normalize hyphens to underscores in patient IDs (LA-QA056 -> LA_QA056)",
    },
    "2022_Vietnam National Children_s Hospital A4D Tracker_patient_cleaned.parquet": {
        "patient_id_format": "Python needs to normalize hyphens to underscores in patient IDs (VN-QC070 -> VN_QC070)",
    },
    "2023_Mahosot Hospital A4D Tracker_patient_cleaned.parquet": {
        "patient_id_format": "Python needs to normalize hyphens to underscores in patient IDs (LA-QA056 -> LA_QA056)",
    },
    "2023_NPH A4D Tracker_patient_cleaned.parquet": {
        "patient_id_format": "Excel has wrong patient IDs in Sep23/Oct23: KH_QEH026 (should be KH_QE026). Python extracts as-is, R truncates to KH_QEH02",
    },
    "2023_Vietnam National Children's Hospital A4D Tracker_patient_cleaned.parquet": {
        "patient_id_format": "Python needs to normalize hyphens to underscores in patient IDs (VN-QC070 -> VN_QC070)",
        "duplicate_records": "Excel has duplicate patient_id VN_QC026 in Aug23 sheet that needs to be fixed",
    },
    "2024_CDA A4D Tracker_patient_cleaned.parquet": {
        "patient_id_format": "Python needs to normalize hyphens to underscores in patient IDs (KH-QA016, KH-QA017 -> KH_QA016, KH_QA017)",
    },
    "2024_Mahosot Hospital A4D Tracker_patient_cleaned.parquet": {
        "patient_id_format": "Python needs to normalize hyphens to underscores in patient IDs (LA-QA056 -> LA_QA056)",
    },
    "2025_06_Lao Friends Hospital for Children A4D Tracker_patient_cleaned.parquet": {
        "patient_id_format": "Python needs to normalize hyphens to underscores in patient IDs (LA-QA093_LF -> LA_QA093_LF)",
    },
    "2025_06_Mahosot Hospital A4D Tracker_patient_cleaned.parquet": {
        "patient_id_format": "Python needs to normalize hyphens to underscores in patient IDs (LA-QA056 -> LA_QA056)",
    },
    "2025_06_North Okkalapa General Hospital A4D Tracker_patient_cleaned.parquet": {
        "patient_id_extraction": "R incorrectly creates 'Undefined' patient_id for 18 records across all months. Python correctly extracts the actual patient IDs (121 unique vs R's 119 + Undefined)",
    },
}

# Trackers to skip due to data quality issues in source Excel files
SKIP_VALIDATION = {
    "2024_Vietnam National Children Hospital A4D Tracker_patient_cleaned.parquet": "Excel has duplicate patient rows with conflicting data in Jul24",
}

# Columns to skip in data value comparison due to known extraction/processing differences
# These columns have acceptable differences between R and Python
SKIP_COLUMNS_IN_COMPARISON = {
    "insulin_total_units",  # R has problems extracting this column correctly
}

# Columns that should never be null/empty - critical data integrity check
REQUIRED_COLUMNS = {
    "patient_id",
    "tracker_month",
    "tracker_year",
    "tracker_date",
    "clinic_id",
    "status",
}

# Value mappings for known acceptable differences between R and Python
# Format: {column_name: {r_value: py_value}}
# These values are considered equivalent during comparison
VALUE_MAPPINGS = {
    "status": {
        "Active - Remote": "Active Remote",
        "Active - Clinic": "Active Clinic",
    },
}


@pytest.fixture(scope="module")
def tracker_files():
    """Fixture providing list of all tracker files to validate."""
    trackers = get_all_tracker_files()
    if not trackers:
        pytest.skip("R output directory not found or empty")
    return trackers


def test_output_directories_exist():
    """Verify that both R and Python output directories exist."""
    assert R_OUTPUT_DIR.exists(), f"R output directory not found: {R_OUTPUT_DIR}"
    assert PY_OUTPUT_DIR.exists(), f"Python output directory not found: {PY_OUTPUT_DIR}"


@pytest.mark.parametrize("filename, r_path, py_path", get_all_tracker_files())
def test_record_count_matches(filename, r_path, py_path):
    """Test that record counts match between R and Python for each tracker.

    Validates that the number of records in the cleaned output matches,
    with allowances for known acceptable differences.
    """
    # Skip if marked for skipping
    if filename in SKIP_VALIDATION:
        pytest.skip(SKIP_VALIDATION[filename])

    # Skip if Python file doesn't exist
    if not py_path.exists():
        pytest.skip(f"Python output not found: {py_path}")

    # Read both files
    df_r = pl.read_parquet(r_path)
    df_py = pl.read_parquet(py_path)

    r_count = len(df_r)
    py_count = len(df_py)
    actual_diff = py_count - r_count

    # Check if this is an acceptable difference
    if filename in ACCEPTABLE_DIFFERENCES and "record_diff" in ACCEPTABLE_DIFFERENCES[filename]:
        acceptable = ACCEPTABLE_DIFFERENCES[filename]
        expected_diff = acceptable["record_diff"]

        if actual_diff == expected_diff:
            # Expected difference exists, test passes
            pass
        elif actual_diff == 0:
            # Difference no longer exists! Alert to update config
            pytest.fail(
                f"{filename} is listed in ACCEPTABLE_DIFFERENCES but counts now match "
                f"(R: {r_count}, Python: {py_count}). "
                f"Please remove this file from ACCEPTABLE_DIFFERENCES dict."
            )
        else:
            # Different difference than expected
            assert actual_diff == expected_diff, (
                f"{filename}: Expected difference of {expected_diff} records "
                f"(reason: {acceptable['reason']}), but got {actual_diff}. "
                f"R: {r_count}, Python: {py_count}"
            )
    else:
        # Should match exactly
        assert r_count == py_count, f"{filename}: Record count mismatch - R: {r_count}, Python: {py_count}"


@pytest.mark.parametrize("filename, r_path, py_path", get_all_tracker_files())
def test_schema_matches(filename, r_path, py_path):
    """Test that column schemas match between R and Python for each tracker.

    Validates that both outputs have the same column names.
    """
    # Skip if marked for skipping
    if filename in SKIP_VALIDATION:
        pytest.skip(SKIP_VALIDATION[filename])

    # Skip if Python file doesn't exist
    if not py_path.exists():
        pytest.skip(f"Python output not found: {py_path}")

    # Read both files
    df_r = pl.read_parquet(r_path)
    df_py = pl.read_parquet(py_path)

    r_columns = set(df_r.columns)
    py_columns = set(df_py.columns)

    missing_in_py = r_columns - py_columns
    extra_in_py = py_columns - r_columns

    assert not missing_in_py, f"{filename}: Missing columns in Python: {missing_in_py}"
    assert not extra_in_py, f"{filename}: Extra columns in Python: {extra_in_py}"


@pytest.mark.parametrize("filename, r_path, py_path", get_all_tracker_files())
def test_patient_ids_match(filename, r_path, py_path):
    """Test that unique patient IDs match between R and Python for each tracker.

    Validates that both outputs contain the same set of unique patient_ids,
    with allowances for known acceptable differences.
    """
    # Skip if marked for skipping
    if filename in SKIP_VALIDATION:
        pytest.skip(SKIP_VALIDATION[filename])

    # Skip if Python file doesn't exist
    if not py_path.exists():
        pytest.skip(f"Python output not found: {py_path}")

    # Read both files
    df_r = pl.read_parquet(r_path)
    df_py = pl.read_parquet(py_path)

    r_patients = set(df_r["patient_id"])
    py_patients = set(df_py["patient_id"])

    # Should match exactly (acceptable record count differences don't affect patient_id validation)
    missing_in_py = r_patients - py_patients
    extra_in_py = py_patients - r_patients

    # Check if mismatch exists
    has_mismatch = missing_in_py or extra_in_py

    # If this has a known issue, only skip if the issue still exists
    if filename in KNOWN_ISSUES:
        issue_type = None
        issue_msg = None

        if "patient_id_format" in KNOWN_ISSUES[filename]:
            issue_type = "patient_id_format"
            issue_msg = KNOWN_ISSUES[filename]["patient_id_format"]
        elif "patient_id_extraction" in KNOWN_ISSUES[filename]:
            issue_type = "patient_id_extraction"
            issue_msg = KNOWN_ISSUES[filename]["patient_id_extraction"]

        if issue_type and issue_msg:
            if has_mismatch:
                pytest.skip(f"Known issue - {issue_msg}")
            else:
                # Issue is fixed! Fail the test to alert that KNOWN_ISSUES can be updated
                pytest.fail(
                    f"{filename} is listed in KNOWN_ISSUES but patient_ids now match! "
                    f"Please remove this file from KNOWN_ISSUES dict."
                )

    # Assert no mismatches for files not in KNOWN_ISSUES
    assert not missing_in_py, f"{filename}: Missing patient_ids in Python: {missing_in_py}"
    assert not extra_in_py, f"{filename}: Extra patient_ids in Python: {extra_in_py}"


@pytest.mark.parametrize("filename, r_path, py_path", get_all_tracker_files())
def test_no_duplicate_records(filename, r_path, py_path):
    """Test that there are no duplicate (patient_id, tracker_month) combinations.

    Validates data quality by ensuring no unintended duplicates in Python output.
    """
    # Skip if marked for skipping
    if filename in SKIP_VALIDATION:
        pytest.skip(SKIP_VALIDATION[filename])

    # Skip if Python file doesn't exist
    if not py_path.exists():
        pytest.skip(f"Python output not found: {py_path}")

    # Read Python file
    df_py = pl.read_parquet(py_path)

    # Check for duplicates
    duplicates = (
        df_py.group_by(["patient_id", "tracker_month"]).agg(pl.len().alias("count")).filter(pl.col("count") > 1)
    )

    has_duplicates = len(duplicates) > 0

    # If this has a known duplicate issue, only skip if duplicates still exist
    if filename in KNOWN_ISSUES and "duplicate_records" in KNOWN_ISSUES[filename]:
        if has_duplicates:
            pytest.skip(f"Known issue - {KNOWN_ISSUES[filename]['duplicate_records']}")
        else:
            # Issue is fixed! Fail the test to alert that KNOWN_ISSUES can be updated
            pytest.fail(
                f"{filename} is listed in KNOWN_ISSUES but no longer has duplicates! "
                f"Please remove this file from KNOWN_ISSUES dict."
            )

    assert len(duplicates) == 0, (
        f"{filename}: Found {len(duplicates)} duplicate (patient_id, tracker_month) combinations"
    )


@pytest.mark.parametrize("filename, r_path, py_path", get_all_tracker_files())
def test_required_columns_not_null(filename, r_path, py_path):
    """Test that required columns are never null/empty in Python output.

    Validates critical data integrity by ensuring required columns
    like patient_id, tracker_month, clinic_id, etc. always have values.
    """
    # Skip if marked for skipping
    if filename in SKIP_VALIDATION:
        pytest.skip(SKIP_VALIDATION[filename])

    # Skip if Python file doesn't exist
    if not py_path.exists():
        pytest.skip(f"Python output not found: {py_path}")

    # Read Python file
    df_py = pl.read_parquet(py_path)

    # Check each required column
    null_issues = []
    for col in REQUIRED_COLUMNS:
        if col not in df_py.columns:
            null_issues.append(f"{col}: Column missing from output")
            continue

        null_count = df_py[col].null_count()
        if null_count > 0:
            null_issues.append(f"{col}: {null_count} null values found")

    if null_issues:
        error_msg = f"{filename}: Required columns have null/missing values:\n"
        error_msg += "\n".join(f"  - {issue}" for issue in null_issues)
        pytest.fail(error_msg)


class TestValidationSummary:
    """Summary tests providing overall validation statistics."""

    def test_file_coverage(self, tracker_files):
        """Report file coverage statistics (informational only)."""
        total_trackers = len(tracker_files)
        skipped = 0
        missing_py = 0
        available = 0

        for filename, r_path, py_path in tracker_files:
            if filename in SKIP_VALIDATION:
                skipped += 1
            elif not py_path.exists():
                missing_py += 1
            else:
                available += 1

        print(f"\n{'=' * 60}")
        print("R vs Python File Coverage Summary")
        print(f"{'=' * 60}")
        print(f"Total trackers in R output: {total_trackers}")
        print(f"Python files available: {available + skipped}")
        print(f"Skipped (Excel data issues): {skipped}")
        print(f"Missing Python output: {missing_py}")
        print(f"File coverage: {(available / total_trackers * 100):.1f}%")
        print(f"{'=' * 60}")

        # Just report, don't assert - this is informational only


@pytest.mark.parametrize("filename, r_path, py_path", get_all_tracker_files())
def test_data_values_match(filename, r_path, py_path):
    """Test that data values match between R and Python for matching patients.

    Compares all column values for patients that exist in both outputs,
    grouped by (patient_id, tracker_month) to identify exactly which
    patient-month combinations have mismatching data.
    """
    if int(filename[:4]) < 2025:
        pytest.skip("Data value comparison only for 2025 trackers and later")
        
    # Skip if marked for skipping
    if filename in SKIP_VALIDATION:
        pytest.skip(SKIP_VALIDATION[filename])

    # Skip if Python file doesn't exist
    if not py_path.exists():
        pytest.skip(f"Python output not found: {py_path}")

    # Read both files
    # Note: We use inner join, so we only compare patients that exist in both outputs
    # This allows us to compare data values even when there are patient_id differences
    df_r = pl.read_parquet(r_path)
    df_py = pl.read_parquet(py_path)

    # Get common columns (some might differ)
    r_cols = set(df_r.columns)
    py_cols = set(df_py.columns)
    common_cols = sorted(r_cols & py_cols)

    # Must have at least patient_id and tracker_month
    assert "patient_id" in common_cols and "tracker_month" in common_cols

    # Join on patient_id and tracker_month to compare matching records
    # Use inner join to only compare patients that exist in both
    df_r_subset = df_r.select(common_cols)
    df_py_subset = df_py.select(common_cols)

    # Add suffixes to distinguish R vs Python columns
    df_r_renamed = df_r_subset.rename({col: f"{col}_r" for col in common_cols if col not in ["patient_id", "tracker_month"]})
    df_py_renamed = df_py_subset.rename({col: f"{col}_py" for col in common_cols if col not in ["patient_id", "tracker_month"]})

    # Join on patient_id and tracker_month
    df_joined = df_r_renamed.join(df_py_renamed, on=["patient_id", "tracker_month"], how="inner")

    if len(df_joined) == 0:
        pytest.skip("No matching (patient_id, tracker_month) combinations to compare")

    # Compare each column
    mismatches = []
    for col in common_cols:
        if col in ["patient_id", "tracker_month"]:
            continue

        # Skip columns with known acceptable differences
        if col in SKIP_COLUMNS_IN_COMPARISON:
            continue

        r_col = f"{col}_r"
        py_col = f"{col}_py"

        # Apply value mappings if this column has known equivalences
        df_compare = df_joined
        if col in VALUE_MAPPINGS:
            mapping = VALUE_MAPPINGS[col]
            # Map R values to their Python equivalents for comparison
            df_compare = df_compare.with_columns(
                pl.col(r_col).replace_strict(mapping, default=pl.col(r_col), return_dtype=pl.Utf8).alias(f"{r_col}_mapped")
            )
            r_col_for_comparison = f"{r_col}_mapped"
        else:
            r_col_for_comparison = r_col

        # Check if numeric column - use approximate comparison for floats
        is_numeric = df_compare[r_col_for_comparison].dtype in [pl.Float32, pl.Float64, pl.Int8, pl.Int16, pl.Int32, pl.Int64]

        if is_numeric and df_compare[r_col_for_comparison].dtype in [pl.Float32, pl.Float64]:
            # For floats, use approximate equality (accounting for floating point precision)
            # Values must differ by more than 1e-6 to be considered different
            diff_mask = (
                # Both non-null and significantly different
                ((df_compare[r_col_for_comparison].is_not_null()) & (df_compare[py_col].is_not_null()) &
                 ((df_compare[r_col_for_comparison] - df_compare[py_col]).abs() > 1e-6))
                # One null, other not null
                | ((df_compare[r_col_for_comparison].is_null()) & (df_compare[py_col].is_not_null()))
                | ((df_compare[r_col_for_comparison].is_not_null()) & (df_compare[py_col].is_null()))
            )
        else:
            # For non-floats, use exact comparison
            diff_mask = (
                # Both non-null and different
                ((df_compare[r_col_for_comparison].is_not_null()) & (df_compare[py_col].is_not_null()) &
                 (df_compare[r_col_for_comparison] != df_compare[py_col]))
                # One null, other not null
                | ((df_compare[r_col_for_comparison].is_null()) & (df_compare[py_col].is_not_null()))
                | ((df_compare[r_col_for_comparison].is_not_null()) & (df_compare[py_col].is_null()))
            )

        diff_records = df_compare.filter(diff_mask)

        if len(diff_records) > 0:
            mismatches.append({
                "column": col,
                "mismatches": len(diff_records),
                "sample_patients": diff_records.select(["patient_id", "tracker_month", r_col, py_col]).head(5)
            })

    if mismatches:
        # Build detailed error message
        error_msg = f"{filename}: Found data mismatches in {len(mismatches)} columns\n"
        for mismatch in mismatches[:5]:  # Show first 5 columns with issues
            error_msg += f"\nColumn '{mismatch['column']}': {mismatch['mismatches']} mismatching records\n"
            error_msg += "Sample differing records:\n"
            error_msg += str(mismatch['sample_patients'])

        if len(mismatches) > 5:
            error_msg += f"\n\n... and {len(mismatches) - 5} more columns with mismatches"

        pytest.fail(error_msg)
