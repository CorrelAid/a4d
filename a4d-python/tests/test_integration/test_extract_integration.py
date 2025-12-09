"""Integration tests for patient data extraction.

Tests extraction on real tracker files, validating:
- Correct number of rows extracted
- Correct number of columns
- Month sheets are processed correctly
- Annual and Patient List sheets are handled (if present)
- Metadata columns are added correctly
"""

import pytest

from a4d.extract.patient import read_all_patient_sheets

from .conftest import skip_if_missing

pytestmark = [pytest.mark.slow, pytest.mark.integration]


class TestExtract2024Penang:
    """Test extraction on 2024 Penang tracker (has Annual + Patient List)."""

    def test_extract_total_rows(self, tracker_2024_penang):
        """Should extract all patient records from all sheets."""
        skip_if_missing(tracker_2024_penang)

        df = read_all_patient_sheets(tracker_2024_penang)

        # 2024 Penang has 12 month sheets + data from Patient List
        assert len(df) == 174
        assert len(df.columns) > 0  # Should have columns (exact count varies before cleaning)

    def test_extract_has_metadata_columns(self, tracker_2024_penang):
        """Should add metadata columns (tracker_year, tracker_month, sheet_name, file_name)."""
        skip_if_missing(tracker_2024_penang)

        df = read_all_patient_sheets(tracker_2024_penang)

        assert "tracker_year" in df.columns
        assert "tracker_month" in df.columns
        assert "sheet_name" in df.columns
        assert "file_name" in df.columns
        assert "clinic_id" in df.columns

    def test_extract_year_is_correct(self, tracker_2024_penang):
        """Should extract year 2024 from sheet names."""
        skip_if_missing(tracker_2024_penang)

        df = read_all_patient_sheets(tracker_2024_penang)

        # All rows should have year 2024
        assert df["tracker_year"].unique().to_list() == [2024]

    def test_extract_has_12_months(self, tracker_2024_penang):
        """Should process 12 month sheets (Jan-Dec 2024)."""
        skip_if_missing(tracker_2024_penang)

        df = read_all_patient_sheets(tracker_2024_penang)

        months = sorted(df["tracker_month"].unique().to_list())
        expected_months = list(range(1, 13))  # 1-12
        assert months == expected_months

    def test_extract_clinic_id(self, tracker_2024_penang):
        """Should extract clinic_id from parent directory."""
        skip_if_missing(tracker_2024_penang)

        df = read_all_patient_sheets(tracker_2024_penang)

        # Parent directory is PNG
        assert df["clinic_id"].unique().to_list() == ["PNG"]


class TestExtract2023Sibu:
    """Test extraction on 2023 Sibu tracker (edge case with duplicate columns)."""

    def test_extract_handles_duplicates(self, tracker_2023_sibu):
        """Should handle duplicate column mappings (complication_screening)."""
        skip_if_missing(tracker_2023_sibu)

        # This should not raise DuplicateError
        df = read_all_patient_sheets(tracker_2023_sibu)

        assert len(df) == 14  # 2023 Sibu has 14 total records
        assert len(df.columns) > 0

    def test_extract_year_2023(self, tracker_2023_sibu):
        """Should extract year 2023."""
        skip_if_missing(tracker_2023_sibu)

        df = read_all_patient_sheets(tracker_2023_sibu)

        assert df["tracker_year"].unique().to_list() == [2023]

    def test_extract_months_sep_to_dec(self, tracker_2023_sibu):
        """Should extract months Sep-Dec 2023."""
        skip_if_missing(tracker_2023_sibu)

        df = read_all_patient_sheets(tracker_2023_sibu)

        months = sorted(df["tracker_month"].unique().to_list())
        expected_months = [9, 10, 11, 12]  # Sep-Dec
        assert months == expected_months


class TestExtract2022PenangLegacy:
    """Test extraction on 2022 Penang (legacy format without Annual sheet)."""

    def test_extract_legacy_format(self, tracker_2022_penang):
        """Should handle legacy format without Annual sheet."""
        skip_if_missing(tracker_2022_penang)

        df = read_all_patient_sheets(tracker_2022_penang)

        assert len(df) == 156  # 2022 Penang has 156 total records
        assert len(df.columns) > 0

    def test_extract_legacy_has_patient_list(self, tracker_2022_penang):
        """Should still process Patient List sheet in legacy format."""
        skip_if_missing(tracker_2022_penang)

        df = read_all_patient_sheets(tracker_2022_penang)

        # Should have data from Patient List (static columns like dob, province)
        # Check if we have any of the Patient List specific columns
        assert "dob" in df.columns or "province" in df.columns

    def test_extract_legacy_year_2022(self, tracker_2022_penang):
        """Should extract year 2022."""
        skip_if_missing(tracker_2022_penang)

        df = read_all_patient_sheets(tracker_2022_penang)

        assert df["tracker_year"].unique().to_list() == [2022]
