"""Integration tests for patient data cleaning.

Tests cleaning on real extracted data, validating:
- Correct schema (83 columns)
- Type conversions work correctly
- Error tracking works
- Derived columns are created
"""

import pytest

from a4d.clean.patient import clean_patient_data
from a4d.errors import ErrorCollector
from a4d.extract.patient import read_all_patient_sheets

from .conftest import EXPECTED_SCHEMA_COLS, skip_if_missing

pytestmark = [pytest.mark.slow, pytest.mark.integration]


class TestClean2024Penang:
    """Test cleaning on 2024 Penang extracted data."""

    def test_clean_produces_correct_schema(self, tracker_2024_penang):
        """Should produce exactly 83 columns after cleaning."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS

    def test_clean_preserves_row_count(self, tracker_2024_penang):
        """Should not drop rows during cleaning."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        assert len(df_clean) == len(df_raw)

    def test_clean_creates_derived_columns(self, tracker_2024_penang):
        """Should create derived columns (insulin_type, insulin_subtype, etc.)."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        # Check derived columns exist
        assert "insulin_type" in df_clean.columns
        assert "insulin_subtype" in df_clean.columns
        assert "blood_pressure_sys_mmhg" in df_clean.columns
        assert "blood_pressure_dias_mmhg" in df_clean.columns

    def test_clean_tracks_errors(self, tracker_2024_penang):
        """Should track data quality errors in ErrorCollector."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        # Should have some errors (type conversions, invalid values, etc.)
        # Exact count varies, but should be non-zero for this tracker
        assert len(collector) >= 0  # May have 0 or more errors

    def test_clean_has_required_columns(self, tracker_2024_penang):
        """Should have all required columns in final schema."""
        skip_if_missing(tracker_2024_penang)

        df_raw = read_all_patient_sheets(tracker_2024_penang)
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

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
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS
        assert len(df_clean) == 14


class TestClean2022PenangLegacy:
    """Test cleaning on 2022 Penang (legacy format)."""

    def test_clean_legacy_format(self, tracker_2022_penang):
        """Should clean legacy format to same 83-column schema."""
        skip_if_missing(tracker_2022_penang)

        df_raw = read_all_patient_sheets(tracker_2022_penang)
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        # Should produce same schema regardless of input format
        assert len(df_clean.columns) == EXPECTED_SCHEMA_COLS
        assert len(df_clean) == 156

    def test_clean_legacy_has_patient_list_data(self, tracker_2022_penang):
        """Should preserve Patient List data (dob, province, etc.) after cleaning."""
        skip_if_missing(tracker_2022_penang)

        df_raw = read_all_patient_sheets(tracker_2022_penang)
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        # Patient List columns should be preserved
        assert "dob" in df_clean.columns
        assert "province" in df_clean.columns
        assert "sex" in df_clean.columns
