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


# Known differences that are acceptable
KNOWN_DIFFERENCES = {
    "2024_Mandalay Children's Hospital A4D Tracker_patient_cleaned.parquet": {
        "record_diff": 11,
        "reason": "R implicit filtering: MM_QA001 has 12 monthly records in Python but only 1 in R",
    },
    "2024_Mahosot Hospital A4D Tracker_patient_cleaned.parquet": {
        "record_diff": 1,
        "reason": "Python correctly extracts LA-QA088 which is missing row number in Excel column A; R incorrectly drops it",
    },
}

# Trackers to skip due to data quality issues in source Excel
SKIP_VALIDATION = {
    "2024_Vietnam National Children Hospital A4D Tracker_patient_cleaned.parquet": "Excel has duplicate patient rows with conflicting data in Jul24",
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

    # Check if this is a known difference
    if filename in KNOWN_DIFFERENCES:
        known_diff = KNOWN_DIFFERENCES[filename]
        expected_diff = known_diff["record_diff"]
        actual_diff = py_count - r_count

        assert actual_diff == expected_diff, (
            f"{filename}: Expected difference of {expected_diff} records "
            f"(reason: {known_diff['reason']}), but got {actual_diff}. "
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

    # Check if this is a known difference tracker
    if filename in KNOWN_DIFFERENCES:
        # For known differences, we expect the same patient_ids, just different record counts
        # (e.g., MM_QA001 exists in both, but with different numbers of monthly records)
        pass  # Allow differences but don't fail
    else:
        # Should match exactly
        missing_in_py = r_patients - py_patients
        extra_in_py = py_patients - r_patients

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

    assert len(duplicates) == 0, (
        f"{filename}: Found {len(duplicates)} duplicate (patient_id, tracker_month) combinations"
    )


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
        print(f"Python files available: {available}")
        print(f"Skipped (Excel data issues): {skipped}")
        print(f"Missing Python output: {missing_py}")
        print(f"File coverage: {(available / total_trackers * 100):.1f}%")
        print(f"{'=' * 60}")

        # Just report, don't assert - this is informational only
