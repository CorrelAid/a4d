"""Tests for patient data extraction."""

from pathlib import Path

import pytest

from a4d.extract.patient import (
    extract_patient_data,
    find_month_sheets,
    get_tracker_year,
)


def column_letter_to_index(col_letter: str) -> int:
    """Convert Excel column letter to 0-based index.

    Examples:
        A -> 0, B -> 1, Z -> 25, AA -> 26, AB -> 27, AC -> 28
    """
    result = 0
    for char in col_letter:
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1


def calculate_expected_columns(start_col: str, end_col: str) -> int:
    """Calculate expected number of columns from Excel range.

    Args:
        start_col: Starting column letter (e.g., 'B')
        end_col: Ending column letter (e.g., 'AC')

    Returns:
        Number of columns in the range

    Examples:
        B to Z: 25 columns
        B to AC: 28 columns
        B to AB: 27 columns
    """
    start_idx = column_letter_to_index(start_col)
    end_idx = column_letter_to_index(end_col)
    return end_idx - start_idx + 1

# Test data paths
TRACKER_2024 = Path(
    "/Volumes/USB SanDisk 3.2Gen1 Media/A4D/data/a4dphase2_upload/"
    "Malaysia/SBU/2024_Sibu Hospital A4D Tracker.xlsx"
)
TRACKER_2019 = Path(
    "/Volumes/USB SanDisk 3.2Gen1 Media/A4D/data/a4dphase2_upload/"
    "Malaysia/PNG/2019_Penang General Hospital A4D Tracker_DC.xlsx"
)
TRACKER_2018 = Path(
    "/Volumes/USB SanDisk 3.2Gen1 Media/A4D/data/a4dphase2_upload/"
    "Malaysia/PNG/2018_Penang General Hospital A4D Tracker_DC.xlsx"
)


@pytest.mark.skipif(not TRACKER_2024.exists(), reason="Tracker file not available")
def test_get_tracker_year_from_sheet_names():
    """Test extracting year from sheet names."""
    year = get_tracker_year(TRACKER_2024, ["Jan24", "Feb24", "Mar24"])
    assert year == 2024


@pytest.mark.skipif(not TRACKER_2024.exists(), reason="Tracker file not available")
def test_get_tracker_year_from_filename():
    """Test extracting year from filename as fallback."""
    year = get_tracker_year(TRACKER_2024, ["January", "February"])
    assert year == 2024


@pytest.mark.skipif(not TRACKER_2024.exists(), reason="Tracker file not available")
def test_find_month_sheets_2024():
    """Test finding month sheets in 2024 tracker."""
    from openpyxl import load_workbook

    wb = load_workbook(TRACKER_2024, data_only=True)
    month_sheets = find_month_sheets(wb)

    assert len(month_sheets) > 0
    assert any("Jan" in sheet for sheet in month_sheets)
    assert any("Dec" in sheet for sheet in month_sheets)


# Parameterized test data: (tracker_file, sheet_name, year, expected_patients, expected_cols, notes)
# Note: expected_cols is the actual number after filtering out None header columns
TRACKER_TEST_CASES = [
    # 2024 tracker - optimized single-pass extraction
    (TRACKER_2024, "Jan24", 2024, 4, 31, "Single-pass read-only"),

    # 2019 tracker - format changes across months! Optimized extraction
    (TRACKER_2019, "Jan19", 2019, 10, 25, "Single-pass read-only"),
    (TRACKER_2019, "Feb19", 2019, 10, 28, "Single-pass read-only"),
    (TRACKER_2019, "Mar19", 2019, 10, 27, "Single-pass read-only"),
    (TRACKER_2019, "Oct19", 2019, 11, 27, "Single-pass read-only"),

    # 2018 tracker - single-line headers
    (TRACKER_2018, "Dec18", 2018, 10, 19, "Single-pass read-only"),
]


@pytest.mark.skipif(
    not TRACKER_2024.exists() or not TRACKER_2019.exists() or not TRACKER_2018.exists(),
    reason="Tracker files not available"
)
@pytest.mark.parametrize(
    "tracker_file,sheet_name,year,expected_patients,expected_cols,notes",
    TRACKER_TEST_CASES,
    ids=lambda params: f"{params[1] if isinstance(params, tuple) and len(params) > 1 else params}"
)
def test_extract_patient_data_schema(
    tracker_file, sheet_name, year, expected_patients, expected_cols, notes
):
    """Test patient data extraction with schema validation across different months.

    This parameterized test validates that:
    1. Correct number of patients are extracted
    2. Correct number of columns match expected (after filtering None headers)
    3. Format changes between months are handled correctly

    The test is critical because tracker formats change even within the same year,
    and data quality is inconsistent across different months.
    """
    df = extract_patient_data(tracker_file, sheet_name, year)

    # Check dimensions
    assert len(df) == expected_patients, (
        f"{sheet_name}: Expected {expected_patients} patients, got {len(df)}"
    )
    assert len(df.columns) == expected_cols, (
        f"{sheet_name}: Expected {expected_cols} columns ({notes}), got {len(df.columns)}"
    )

    # Verify we have at least Patient ID column
    assert any("patient" in col.lower() and "id" in col.lower() for col in df.columns), (
        f"{sheet_name}: Missing Patient ID column in {df.columns}"
    )

    print(f"\n{sheet_name}: {len(df)} patients × {len(df.columns)} columns ({notes}) ✓")


@pytest.mark.skipif(not TRACKER_2024.exists(), reason="Tracker file not available")
def test_extract_patient_data_2024_detailed():
    """Detailed test for 2024 tracker with patient ID validation."""
    df = extract_patient_data(TRACKER_2024, "Jan24", 2024)

    # Verify specific patient IDs
    patient_ids = df["Patient ID*"].to_list()
    assert patient_ids == ["MY_SU001", "MY_SU002", "MY_SU003", "MY_SU004"], (
        f"Expected MY_SU001-004, got {patient_ids}"
    )

    print(f"\n2024 Jan24 - Patient IDs: {patient_ids} ✓")
