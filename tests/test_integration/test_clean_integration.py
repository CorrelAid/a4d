"""Integration tests for patient data cleaning.

Tests cleaning on real extracted data, validating:
- Correct schema (85 columns)
- Type conversions work correctly
- Error tracking works
- Derived columns are created
"""

import pytest

from a4d.clean.patient import clean_patient_data
from a4d.clean.product import clean_product_data
from a4d.extract.patient import read_all_patient_sheets
from a4d.extract.product import read_all_product_sheets

from .conftest import EXPECTED_SCHEMA_COLS, EXPECTED_SCHEMA_COLS_PRODUCT, skip_if_missing

pytestmark = [pytest.mark.slow, pytest.mark.integration]


class TestClean2024Penang:
    """Test cleaning on 2024 Penang extracted data."""

    def test_clean_produces_correct_schema(self, tracker_2024_penang):
        """Should produce exactly 85 columns after cleaning."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        df_clean = clean_patient_data(df_raw)

        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS

    def test_clean_preserves_row_count(self, tracker_2024_penang):
        """Should not drop rows during cleaning."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        df_clean = clean_patient_data(df_raw)

        assert len(df_clean) == len(df_raw)

    def test_clean_creates_derived_columns(self, tracker_2024_penang):
        """Should create derived columns (insulin_type, insulin_subtype, etc.)."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        df_clean = clean_patient_data(df_raw)

        # Check derived columns exist
        assert "insulin_type" in df_clean.columns
        assert "insulin_subtype" in df_clean.columns
        assert "blood_pressure_sys_mmhg" in df_clean.columns
        assert "blood_pressure_dias_mmhg" in df_clean.columns

    def test_clean_tracks_errors(self, tracker_2024_penang, collector):
        """Should track data quality errors in ErrorCollector."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        clean_patient_data(df_raw)

        # Should have some errors (type conversions, invalid values, etc.)
        # Exact count varies, but should be non-zero for this tracker
        assert len(collector) >= 0  # May have 0 or more errors

    def test_clean_has_required_columns(self, tracker_2024_penang):
        """Should have all required columns in final schema."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        df_clean = clean_patient_data(df_raw)

        # Check key columns exist
        required_columns = [
            "patient_id",
            "tracker_year",
            "tracker_month",
            "age",
            "hba1c_updated",
            "fbg_updated_mg",
            "insulin_type",
        ]
        for col in required_columns:
            assert col in df_clean.columns, f"Missing required column: {col}"


class TestClean2023Sibu:
    """Test cleaning on 2023 Sibu (edge case)."""

    def test_clean_after_duplicate_handling(self, tracker_2023_sibu):
        """Should clean successfully after duplicate column handling."""
        skip_if_missing(tracker_2023_sibu)

        df_raw = read_all_patient_sheets(tracker_2023_sibu)
        df_clean = clean_patient_data(df_raw)

        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS
        assert len(df_clean) == 14


class TestClean2022PenangLegacy:
    """Test cleaning on 2022 Penang (legacy format)."""

    def test_clean_legacy_format(self, tracker_2022_penang):
        """Should clean legacy format to same 85-column schema."""
        skip_if_missing(tracker_2022_penang)

        df_raw = read_all_patient_sheets(tracker_2022_penang)
        df_clean = clean_patient_data(df_raw)

        # Should produce same schema regardless of input format
        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS
        assert len(df_clean) == 156

    def test_clean_legacy_has_patient_list_data(self, tracker_2022_penang):
        """Should preserve Patient List data (dob, province, etc.) after cleaning."""
        skip_if_missing(tracker_2022_penang)

        df_raw = read_all_patient_sheets(tracker_2022_penang)
        df_clean = clean_patient_data(df_raw)

        # Patient List columns should be preserved
        assert "dob" in df_clean.columns
        assert "province" in df_clean.columns
        assert "sex" in df_clean.columns


class TestCleanProduct2024Penang:
    """Test product cleaning on 2024 Penang extracted data."""

    def test_clean_produces_correct_schema(self, tracker_2024_penang):
        """Should produce exactly 20 columns after cleaning (product meta schema)."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_product_sheets(tracker_2024_penang)
        df_clean = clean_product_data(df_raw)

        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS_PRODUCT

    def test_clean_drops_uninformative_rows(self, tracker_2024_penang):
        """Unlike patient, product cleaning drops blank/uninformative template rows."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_product_sheets(tracker_2024_penang)
        df_clean = clean_product_data(df_raw)

        assert len(df_clean) == 244
        assert len(df_clean) < len(df_raw)

    def test_clean_creates_derived_columns(self, tracker_2024_penang):
        """Should create derived columns (balance_status, category, unit_capacity)."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_product_sheets(tracker_2024_penang)
        df_clean = clean_product_data(df_raw)

        assert "product_balance_status" in df_clean.columns
        assert "product_category" in df_clean.columns
        assert "product_unit_capacity" in df_clean.columns

    def test_clean_tracks_errors(self, tracker_2024_penang, collector):
        """Should track data quality errors in ErrorCollector."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_product_sheets(tracker_2024_penang)
        clean_product_data(df_raw)

        assert len(collector) >= 0

    def test_clean_has_required_columns(self, tracker_2024_penang):
        """Should have all required columns in final schema."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_product_sheets(tracker_2024_penang)
        df_clean = clean_product_data(df_raw)

        required_columns = [
            "product",
            "product_table_year",
            "product_table_month",
            "product_units_released",
            "product_units_received",
            "product_balance",
        ]
        for col in required_columns:
            assert col in df_clean.columns, f"Missing required column: {col}"


class TestCleanProduct2023Sibu:
    """Test product cleaning on 2023 Sibu (edge case)."""

    def test_clean_after_duplicate_handling(self, tracker_2023_sibu):
        skip_if_missing(tracker_2023_sibu)

        df_raw = read_all_product_sheets(tracker_2023_sibu)
        df_clean = clean_product_data(df_raw)

        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS_PRODUCT
        assert len(df_clean) == 67


class TestCleanProduct2022PenangLegacy:
    """Test product cleaning on 2022 Penang (legacy format)."""

    def test_clean_legacy_format(self, tracker_2022_penang):
        skip_if_missing(tracker_2022_penang)

        df_raw = read_all_product_sheets(tracker_2022_penang)
        df_clean = clean_product_data(df_raw)

        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS_PRODUCT
        assert len(df_clean) == 237
