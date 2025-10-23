"""Tests for patient data extraction."""

from pathlib import Path

import polars as pl
import pytest

from a4d.extract.patient import (
    extract_patient_data,
    extract_tracker_month,
    find_month_sheets,
    get_tracker_year,
    harmonize_patient_data_columns,
    merge_duplicate_columns_data,
    read_all_patient_sheets,
)


def column_letter_to_index(col_letter: str) -> int:
    """Convert Excel column letter to 0-based index.

    Examples:
        A -> 0, B -> 1, Z -> 25, AA -> 26, AB -> 27, AC -> 28
    """
    result = 0
    for char in col_letter:
        result = result * 26 + (ord(char) - ord("A") + 1)
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
    (
        TRACKER_2024,
        "Jan24",
        2024,
        4,
        calculate_expected_columns("B", "AG") - 1,
        "Single-pass read-only",
    ),
    # 2019 tracker - format changes across months! Optimized extraction
    (
        TRACKER_2019,
        "Jan19",
        2019,
        10,
        calculate_expected_columns("B", "Z"),
        "Single-pass read-only",
    ),
    (
        TRACKER_2019,
        "Feb19",
        2019,
        10,
        calculate_expected_columns("B", "AC"),
        "Single-pass read-only",
    ),
    (
        TRACKER_2019,
        "Mar19",
        2019,
        10,
        calculate_expected_columns("B", "AB"),
        "Single-pass read-only",
    ),
    (
        TRACKER_2019,
        "Oct19",
        2019,
        11,
        calculate_expected_columns("B", "AB"),
        "Single-pass read-only",
    ),
    # 2018 tracker - single-line headers
    (
        TRACKER_2018,
        "Dec18",
        2018,
        10,
        calculate_expected_columns("B", "T"),
        "Single-pass read-only",
    ),
]


@pytest.mark.skipif(
    any(not tf.exists() for tf, _, _, _, _, _ in TRACKER_TEST_CASES),
    reason="Tracker files not available",
)
@pytest.mark.parametrize(
    "tracker_file,sheet_name,year,expected_patients,expected_cols,notes",
    TRACKER_TEST_CASES,
    ids=lambda params: f"{params[1] if isinstance(params, tuple) and len(params) > 1 else params}",
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
    assert patient_ids == ["MY_QI001", "MY_QI002", "MY_QI003", "MY_QI004"], (
        f"Expected MY_QI001-004, got {patient_ids}"
    )

    print(f"\n2024 Jan24 - Patient IDs: {patient_ids} ✓")


def test_harmonize_patient_data_columns_basic():
    """Test basic column harmonization with known synonyms."""
    raw_df = pl.DataFrame(
        {
            "Patient ID*": ["MY_QI001", "MY_QI002"],
            "Age": [25, 30],
            "D.O.B.": ["1998-01-15", "1993-06-20"],
        }
    )

    harmonized = harmonize_patient_data_columns(raw_df)

    # Check that columns were renamed to standardized names
    assert "patient_id" in harmonized.columns
    assert "age" in harmonized.columns
    assert "dob" in harmonized.columns

    # Check that data is preserved
    assert harmonized["patient_id"].to_list() == ["MY_QI001", "MY_QI002"]
    assert harmonized["age"].to_list() == [25, 30]


def test_harmonize_patient_data_columns_multiple_synonyms():
    """Test that multiple columns mapping to same name raises error.

    When multiple columns in the input map to the same standardized name
    (e.g., "Patient ID", "ID", "Patient ID*" all map to "patient_id"),
    Polars will raise a DuplicateError. This is expected behavior.
    """
    raw_df = pl.DataFrame(
        {
            "Patient ID": ["P001"],
            "ID": ["P002"],
            "Patient ID*": ["P003"],
        }
    )

    # Multiple columns mapping to the same standard name should raise error
    with pytest.raises(pl.exceptions.DuplicateError, match="column 'patient_id' is duplicate"):
        harmonize_patient_data_columns(raw_df)


def test_harmonize_patient_data_columns_unmapped_strict_false():
    """Test that unmapped columns are kept when strict=False (default)."""
    raw_df = pl.DataFrame(
        {
            "Patient ID*": ["MY_QI001"],
            "Age": [25],
            "UnknownColumn": ["some value"],
        }
    )

    harmonized = harmonize_patient_data_columns(raw_df, strict=False)

    # Mapped columns should be renamed
    assert "patient_id" in harmonized.columns
    assert "age" in harmonized.columns

    # Unmapped column should be kept as-is
    assert "UnknownColumn" in harmonized.columns


def test_harmonize_patient_data_columns_unmapped_strict_true():
    """Test that unmapped columns raise error when strict=True."""
    raw_df = pl.DataFrame(
        {
            "Patient ID*": ["MY_QI001"],
            "UnknownColumn": ["some value"],
        }
    )

    with pytest.raises(ValueError, match="Unmapped columns found"):
        harmonize_patient_data_columns(raw_df, strict=True)


def test_harmonize_patient_data_columns_empty_dataframe():
    """Test harmonization with empty DataFrame."""
    raw_df = pl.DataFrame()

    harmonized = harmonize_patient_data_columns(raw_df)

    assert len(harmonized) == 0
    assert len(harmonized.columns) == 0


@pytest.mark.skipif(not TRACKER_2024.exists(), reason="Tracker file not available")
def test_harmonize_real_tracker_data():
    """Test harmonization with real tracker data."""
    # Extract raw data
    raw_df = extract_patient_data(TRACKER_2024, "Jan24", 2024)

    # Harmonize columns
    harmonized = harmonize_patient_data_columns(raw_df)

    # Check that key columns were renamed
    assert "patient_id" in harmonized.columns
    assert "age" in harmonized.columns

    # Check that data is preserved
    assert len(harmonized) == len(raw_df)  # Same number of rows
    assert harmonized["patient_id"].to_list() == ["MY_QI001", "MY_QI002", "MY_QI003", "MY_QI004"]


def test_extract_tracker_month():
    """Test extracting month number from sheet name."""
    assert extract_tracker_month("Jan24") == 1
    assert extract_tracker_month("Feb24") == 2
    assert extract_tracker_month("Mar19") == 3
    assert extract_tracker_month("Dec23") == 12

    # Test with ValueError for invalid sheet names
    with pytest.raises(ValueError, match="Could not extract month"):
        extract_tracker_month("Sheet1")


def test_merge_duplicate_columns_data_no_duplicates():
    """Test that data without duplicate headers is unchanged."""
    headers = ["ID", "Name", "Age", "City"]
    data = [["1", "Alice", "25", "NYC"], ["2", "Bob", "30", "LA"]]

    result_headers, result_data = merge_duplicate_columns_data(headers, data)

    assert result_headers == headers
    assert result_data == data


def test_merge_duplicate_columns_data_with_duplicates():
    """Test merging duplicate columns like R's tidyr::unite()."""
    headers = ["ID", "DM Complications", "DM Complications", "DM Complications", "Age"]
    data = [["1", "A", "B", "C", "25"], ["2", "X", "Y", "Z", "30"]]

    result_headers, result_data = merge_duplicate_columns_data(headers, data)

    assert result_headers == ["ID", "DM Complications", "Age"]
    assert result_data == [["1", "A,B,C", "25"], ["2", "X,Y,Z", "30"]]


def test_merge_duplicate_columns_data_with_nulls():
    """Test merging duplicate columns with null values."""
    headers = ["ID", "DM Complications", "DM Complications", "DM Complications", "Age"]
    data = [["1", "A", None, "C", "25"], ["2", None, "Y", None, "30"]]

    result_headers, result_data = merge_duplicate_columns_data(headers, data)

    assert result_headers == ["ID", "DM Complications", "Age"]
    # Empty values are filtered out before joining
    assert result_data == [["1", "A,C", "25"], ["2", "Y", "30"]]


def test_merge_duplicate_columns_data_all_nulls():
    """Test merging when all duplicate columns have null values."""
    headers = ["ID", "DM Complications", "DM Complications", "Age"]
    data = [["1", None, None, "25"]]

    result_headers, result_data = merge_duplicate_columns_data(headers, data)

    assert result_headers == ["ID", "DM Complications", "Age"]
    # All nulls result in None
    assert result_data == [["1", None, "25"]]


def test_merge_duplicate_columns_data_multiple_groups():
    """Test merging multiple groups of duplicate columns."""
    headers = ["ID", "Status", "Status", "Value", "Value", "Value", "Name"]
    data = [["1", "A", "B", "X", "Y", "Z", "Alice"]]

    result_headers, result_data = merge_duplicate_columns_data(headers, data)

    assert result_headers == ["ID", "Status", "Value", "Name"]
    assert result_data == [["1", "A,B", "X,Y,Z", "Alice"]]


@pytest.mark.skipif(not TRACKER_2024.exists(), reason="Tracker file not available")
def test_read_all_patient_sheets_2024():
    """Test reading all patient sheets from 2024 tracker."""
    df_all = read_all_patient_sheets(TRACKER_2024)

    # Check that we have data
    assert len(df_all) > 0, "Should have extracted patient data"

    # Check that metadata columns were added
    assert "sheet_name" in df_all.columns
    assert "tracker_month" in df_all.columns
    assert "tracker_year" in df_all.columns
    assert "file_name" in df_all.columns

    # Check that we have data from multiple months
    unique_months = df_all["tracker_month"].unique().to_list()
    assert len(unique_months) > 1, "Should have data from multiple months"

    # Check that year is correct
    assert all(year == 2024 for year in df_all["tracker_year"].unique().to_list())

    # Check that patient_id column exists
    assert "patient_id" in df_all.columns

    # Check that we filtered out invalid rows (no null patient_ids)
    assert df_all["patient_id"].null_count() == 0

    print(f"\n2024 Tracker: {len(df_all)} total patients from {len(unique_months)} months ✓")


@pytest.mark.skipif(not TRACKER_2019.exists(), reason="Tracker file not available")
def test_read_all_patient_sheets_2019():
    """Test reading all patient sheets from 2019 tracker (different formats across months)."""
    df_all = read_all_patient_sheets(TRACKER_2019)

    # Check that we have data
    assert len(df_all) > 0, "Should have extracted patient data"

    # Check metadata columns
    assert "sheet_name" in df_all.columns
    assert "tracker_month" in df_all.columns
    assert "tracker_year" in df_all.columns

    # Check that year is correct
    assert all(year == 2019 for year in df_all["tracker_year"].unique().to_list())

    # Check that patient_id column exists
    assert "patient_id" in df_all.columns

    # Check that we filtered out invalid rows
    assert df_all["patient_id"].null_count() == 0

    # 2019 tracker has format changes across months - verify we handled them
    unique_months = df_all["tracker_month"].unique().to_list()
    print(f"\n2019 Tracker: {len(df_all)} total patients from {len(unique_months)} months ✓")


@pytest.mark.skipif(not TRACKER_2024.exists(), reason="Tracker file not available")
def test_read_all_patient_sheets_file_name():
    """Test that file_name metadata is correctly added."""
    df_all = read_all_patient_sheets(TRACKER_2024)

    # Check that file_name column exists and matches the tracker file
    assert "file_name" in df_all.columns
    file_names = df_all["file_name"].unique().to_list()
    assert len(file_names) == 1  # All rows should have same file name
    assert file_names[0] == TRACKER_2024.name
