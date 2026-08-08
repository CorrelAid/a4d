"""End-to-end integration tests for the full pipeline (extraction + cleaning).

Tests the complete workflow on real tracker files, validating:
- Extraction + Cleaning work together correctly
- Final output has correct schema and row counts
- Different tracker formats (2024, 2023, 2022) all produce consistent output
"""

import pytest

from a4d.clean.patient import clean_patient_data
from a4d.clean.product import clean_product_data
from a4d.errors import ErrorCollector
from a4d.extract.patient import read_all_patient_sheets
from a4d.extract.product import read_all_product_sheets

from .conftest import EXPECTED_SCHEMA_COLS, EXPECTED_SCHEMA_COLS_PRODUCT, skip_if_missing

pytestmark = [pytest.mark.slow, pytest.mark.integration, pytest.mark.e2e]


@pytest.mark.parametrize(
    ("tracker_fixture", "expected_rows", "expected_year", "description"),
    [
        ("tracker_2024_penang", 174, 2024, "2024 Penang - Annual + Patient List"),
        ("tracker_2024_isdfi", 70, 2024, "2024 ISDFI Philippines"),
        ("tracker_2023_sibu", 14, 2023, "2023 Sibu - duplicate columns edge case"),
        ("tracker_2022_penang", 156, 2022, "2022 Penang - legacy format"),
    ],
)
def test_e2e_pipeline(tracker_fixture, expected_rows, expected_year, description, request):
    """Test full pipeline (extract + clean) on various tracker formats.

    This test validates that:
    1. Extraction works and produces expected row count
    2. Cleaning works and produces 83-column schema
    3. Row count is preserved through the pipeline
    4. Year is extracted correctly
    """
    tracker_path = request.getfixturevalue(tracker_fixture)
    skip_if_missing(tracker_path)

    # Step 1: Extract
    df_raw = read_all_patient_sheets(tracker_path)
    assert len(df_raw) == expected_rows, f"Extraction failed for {description}"

    # Step 2: Clean
    collector = ErrorCollector()
    df_clean = clean_patient_data(df_raw, collector)

    # Validate final output
    assert len(df_clean) == expected_rows, f"Cleaning changed row count for {description}"
    assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS, f"Schema incorrect for {description}"
    assert df_clean["tracker_year"].unique().to_list() == [expected_year], (
        f"Year incorrect for {description}"
    )


class TestE2E2024Penang:
    """Detailed end-to-end test for 2024 Penang tracker."""

    def test_e2e_full_pipeline(self, tracker_2024_penang):
        """Test complete pipeline with detailed validations."""
        skip_if_missing(tracker_2024_penang)

        # Extract
        df_raw = read_all_patient_sheets(tracker_2024_penang)
        assert len(df_raw) == 174

        # Clean
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        # Validate schema
        assert len(df_clean.columns) == 83
        assert len(df_clean) == 174

        # Validate metadata
        assert "tracker_year" in df_clean.columns
        assert "tracker_month" in df_clean.columns
        assert "clinic_id" in df_clean.columns

        # Validate year and months
        assert df_clean["tracker_year"].unique().to_list() == [2024]
        months = sorted(df_clean["tracker_month"].unique().to_list())
        assert months == list(range(1, 13))  # Should have all 12 months

        # Validate clinic_id
        assert df_clean["clinic_id"].unique().to_list() == ["PNG"]

    def test_e2e_critical_columns_populated(self, tracker_2024_penang):
        """Validate that critical columns are fully populated after pipeline."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        # These columns must be 100% populated for every row
        required_full = [
            "patient_id",
            "status",
            "clinic_id",
            "tracker_year",
            "tracker_month",
        ]
        for col in required_full:
            null_count = df_clean[col].is_null().sum()
            assert null_count == 0, f"{col} has {null_count} null values, expected 0"

        # These columns should have high population (allow some nulls)
        required_partial = ["age", "last_clinic_visit_date"]
        for col in required_partial:
            non_null = df_clean[col].is_not_null().sum()
            assert non_null > len(df_clean) * 0.9, f"{col} has <90% population"


class TestE2ECrosYearConsistency:
    """Test that different years produce consistent schemas."""

    def test_all_years_produce_same_schema(
        self, tracker_2024_penang, tracker_2023_sibu, tracker_2022_penang
    ):
        """All tracker years should produce the same 83-column schema."""
        trackers = [
            (tracker_2024_penang, "2024_Penang"),
            (tracker_2023_sibu, "2023_Sibu"),
            (tracker_2022_penang, "2022_Penang"),
        ]

        column_names_per_tracker = {}

        for tracker_path, name in trackers:
            if not tracker_path.exists():
                pytest.skip(f"Tracker file not found: {tracker_path}")

            # Full pipeline
            df_raw = read_all_patient_sheets(tracker_path)
            collector = ErrorCollector()
            df_clean = clean_patient_data(df_raw, collector)

            # Collect column names
            column_names_per_tracker[name] = set(df_clean.columns)

        # All trackers should have same column names
        if len(column_names_per_tracker) > 1:
            first_columns = list(column_names_per_tracker.values())[0]
            for name, columns in column_names_per_tracker.items():
                assert columns == first_columns, f"{name} has different columns than others"


@pytest.mark.parametrize(
    ("tracker_fixture", "expected_clean_rows", "expected_year", "description"),
    [
        ("tracker_2024_penang", 244, 2024, "2024 Penang - Annual + Patient List"),
        ("tracker_2024_isdfi", 115, 2024, "2024 ISDFI Philippines"),
        ("tracker_2023_sibu", 67, 2023, "2023 Sibu - duplicate columns edge case"),
        ("tracker_2022_penang", 237, 2022, "2022 Penang - legacy format"),
    ],
)
def test_e2e_pipeline_product(
    tracker_fixture, expected_clean_rows, expected_year, description, request
):
    """Test full product pipeline (extract + clean) on various tracker formats.

    Unlike patient, product cleaning drops blank/uninformative template rows,
    so extract and clean row counts differ (see TestCleanProduct2024Penang).
    """
    tracker_path = request.getfixturevalue(tracker_fixture)
    skip_if_missing(tracker_path)

    df_raw = read_all_product_sheets(tracker_path)
    assert len(df_raw) > 0, f"Extraction failed for {description}"

    collector = ErrorCollector()
    df_clean = clean_product_data(df_raw, collector)

    assert len(df_clean) == expected_clean_rows, f"Cleaning row count wrong for {description}"
    assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS_PRODUCT, (
        f"Schema incorrect for {description}"
    )
    assert df_clean["product_table_year"].unique().to_list() == [expected_year], (
        f"Year incorrect for {description}"
    )


class TestE2EProduct2024Penang:
    """Detailed end-to-end test for 2024 Penang tracker (product)."""

    def test_e2e_full_pipeline(self, tracker_2024_penang):
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_product_sheets(tracker_2024_penang)
        assert len(df_raw) == 696

        collector = ErrorCollector()
        df_clean = clean_product_data(df_raw, collector)

        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS_PRODUCT
        assert len(df_clean) == 244

        assert "product_table_year" in df_clean.columns
        assert "product_table_month" in df_clean.columns
        assert "clinic_id" in df_clean.columns

        assert df_clean["product_table_year"].unique().to_list() == [2024]
        assert df_clean["clinic_id"].unique().to_list() == ["PNG"]

    def test_e2e_critical_columns_populated(self, tracker_2024_penang):
        """Validate that critical columns are fully populated after pipeline."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_product_sheets(tracker_2024_penang)
        collector = ErrorCollector()
        df_clean = clean_product_data(df_raw, collector)

        required_full = ["product", "product_table_year", "product_table_month", "clinic_id"]
        for col in required_full:
            null_count = df_clean[col].is_null().sum()
            assert null_count == 0, f"{col} has {null_count} null values, expected 0"


class TestE2EProductCrossYearConsistency:
    """Test that different years produce consistent product schemas."""

    def test_all_years_produce_same_schema(
        self, tracker_2024_penang, tracker_2023_sibu, tracker_2022_penang
    ):
        trackers = [
            (tracker_2024_penang, "2024_Penang"),
            (tracker_2023_sibu, "2023_Sibu"),
            (tracker_2022_penang, "2022_Penang"),
        ]

        column_names_per_tracker = {}

        for tracker_path, name in trackers:
            if not tracker_path.exists():
                pytest.skip(f"Tracker file not found: {tracker_path}")

            df_raw = read_all_product_sheets(tracker_path)
            collector = ErrorCollector()
            df_clean = clean_product_data(df_raw, collector)

            column_names_per_tracker[name] = set(df_clean.columns)

        if len(column_names_per_tracker) > 1:
            first_columns = list(column_names_per_tracker.values())[0]
            for name, columns in column_names_per_tracker.items():
                assert columns == first_columns, f"{name} has different columns than others"
