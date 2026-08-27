"""Tests for column synonym mapper."""

from pathlib import Path

import polars as pl
import pytest
import yaml

from a4d.reference import ColumnMapper, load_patient_mapper, load_product_mapper
from a4d.reference.synonyms import sanitize_str


class TestSanitizeStr:
    """Tests for sanitize_str function."""

    def test_basic_sanitization(self):
        """Test basic sanitization cases."""
        assert sanitize_str("Patient ID") == "patientid"
        assert sanitize_str("Patient ID*") == "patientid"
        assert sanitize_str("Age* On Reporting") == "ageonreporting"

    def test_lowercase_conversion(self):
        """Test lowercase conversion."""
        assert sanitize_str("PATIENT ID") == "patientid"
        assert sanitize_str("Patient Name") == "patientname"

    def test_space_removal(self):
        """Test space removal."""
        assert sanitize_str("Date 2022") == "date2022"
        assert sanitize_str("My Awesome Column") == "myawesomecolumn"

    def test_special_character_removal(self):
        """Test special character removal."""
        assert sanitize_str("Patient ID*") == "patientid"
        assert sanitize_str("My Awesome 1st Column!!") == "myawesome1stcolumn"
        assert sanitize_str("D.O.B.") == "dob"
        assert sanitize_str("Age (Years)") == "ageyears"
        assert sanitize_str("Patient.Name..ANON") == "patientnameanon"

    def test_alphanumeric_preserved(self):
        """Test that alphanumeric characters are preserved."""
        assert sanitize_str("Age1") == "age1"
        assert sanitize_str("test123abc") == "test123abc"

    def test_empty_string(self):
        """Test empty string."""
        assert sanitize_str("") == ""

    def test_only_special_chars(self):
        """Test string with only special characters."""
        assert sanitize_str("***!!!") == ""
        assert sanitize_str("...") == ""


class TestColumnMapper:
    """Tests for ColumnMapper class."""

    @pytest.fixture
    def simple_synonyms(self, tmp_path: Path) -> Path:
        """Create a simple synonym YAML file for testing."""
        synonyms = {
            "age": ["Age", "Age*", "age on reporting"],
            "patient_id": ["ID", "Patient ID", "Patient ID*"],
            "name": ["Patient Name"],
            "province": ["Province"],
            "empty_column": [],  # Column with no synonyms
        }

        yaml_path = tmp_path / "test_synonyms.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(synonyms, f)

        return yaml_path

    @pytest.fixture
    def duplicate_synonyms(self, tmp_path: Path) -> Path:
        """Create synonym YAML with duplicate synonyms."""
        synonyms = {
            "age": ["Age", "Years"],
            "age_at_diagnosis": ["Age", "Age at diagnosis"],  # "Age" duplicated
        }

        yaml_path = tmp_path / "test_duplicates.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(synonyms, f)

        return yaml_path

    def test_init_loads_synonyms(self, simple_synonyms: Path):
        """Test that __init__ loads synonyms from YAML file."""
        mapper = ColumnMapper(simple_synonyms)

        assert len(mapper.synonyms) == 5
        assert "age" in mapper.synonyms
        assert "Age" in mapper.synonyms["age"]
        # After sanitization, some synonyms collapse (e.g., "Age" and "Age*" both become "age")
        assert (
            len(mapper._lookup) == 6
        )  # Sanitized synonyms (age+ageonreporting+id+patientid+patientname+province)

    def test_init_missing_file_raises_error(self):
        """Test that __init__ raises error for missing file."""
        with pytest.raises(FileNotFoundError, match="YAML file not found"):
            ColumnMapper(Path("/nonexistent/file.yaml"))

    def test_build_lookup_creates_reverse_mapping(self, simple_synonyms: Path):
        """Test that reverse lookup is built correctly with SANITIZED keys."""
        mapper = ColumnMapper(simple_synonyms)

        # Lookup uses sanitized keys (lowercase, no spaces, no special chars)
        assert mapper._lookup["age"] == "age"  # "Age" and "Age*" both sanitize to "age"
        assert mapper._lookup["ageonreporting"] == "age"  # "age on reporting" → "ageonreporting"
        assert mapper._lookup["id"] == "patient_id"  # "ID" → "id"
        assert (
            mapper._lookup["patientid"] == "patient_id"
        )  # "Patient ID" and "Patient ID*" → "patientid"

    def test_build_lookup_handles_duplicates(self, duplicate_synonyms: Path):
        """Test that duplicate SANITIZED synonyms log warning and use last definition."""
        mapper = ColumnMapper(duplicate_synonyms)

        # "Age" appears in both age and age_at_diagnosis
        # After sanitization, both become "age" → duplicate!
        # Should map to the last one encountered
        assert "age" in mapper._lookup
        assert mapper._lookup["age"] in ["age", "age_at_diagnosis"]

    def test_get_standard_name(self, simple_synonyms: Path):
        """Test getting standard name for a column."""
        mapper = ColumnMapper(simple_synonyms)

        assert mapper.get_standard_name("Age") == "age"
        assert mapper.get_standard_name("Patient ID*") == "patient_id"
        assert mapper.get_standard_name("unknown_column") == "unknown_column"

    def test_get_standard_name_with_sanitization(self, simple_synonyms: Path):
        """Test that sanitization allows flexible synonym matching."""
        mapper = ColumnMapper(simple_synonyms)

        # All these variants should map to "patient_id" after sanitization
        assert mapper.get_standard_name("Patient ID") == "patient_id"
        assert mapper.get_standard_name("Patient ID*") == "patient_id"
        assert mapper.get_standard_name("PATIENT ID") == "patient_id"
        assert mapper.get_standard_name("patient id") == "patient_id"
        assert mapper.get_standard_name("ID") == "patient_id"

        # Age variants
        assert mapper.get_standard_name("Age") == "age"
        assert mapper.get_standard_name("Age*") == "age"
        assert mapper.get_standard_name("age on reporting") == "age"
        assert mapper.get_standard_name("AGE ON REPORTING") == "age"

        # Test with extra spaces/special chars (should still match)
        assert mapper.get_standard_name("Patient  ID*") == "patient_id"

    def test_rename_columns_basic(self, simple_synonyms: Path):
        """Test basic column renaming."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame(
            {
                "Age": [25, 30],
                "Patient ID": ["P001", "P002"],
                "Province": ["Bangkok", "Hanoi"],
            }
        )

        renamed = mapper.rename_columns(df, sheet_name="Jan24")

        assert "age" in renamed.columns
        assert "patient_id" in renamed.columns
        assert "province" in renamed.columns
        assert "Age" not in renamed.columns

    def test_rename_columns_keeps_unmapped(self, simple_synonyms: Path):
        """Test that unmapped columns are kept by default."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame(
            {
                "Age": [25],
                "UnknownColumn": ["value"],
                "AnotherUnmapped": [42],
            }
        )

        renamed = mapper.rename_columns(df, sheet_name="Jan24")

        assert "age" in renamed.columns
        assert "UnknownColumn" in renamed.columns
        assert "AnotherUnmapped" in renamed.columns

    def test_rename_columns_merges_duplicate_targets(self, simple_synonyms: Path):
        """Several source columns mapping to one canonical name are merged, not dropped.

        The 2023 template splits complication screening into B.P./Kidney/Eye/Foot/
        Lipids sub-columns that all map to `complication_screening`; each carries an
        independent value, so keeping only the first silently discards the rest.
        """
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame(
            {
                "Age": [25, 30, 35],
                "Patient ID": ["P001", None, "P003"],
                "ID": [None, "P002", "P003b"],
            }
        )

        renamed = mapper.rename_columns(df, sheet_name="Jan24")

        assert list(renamed.columns) == ["age", "patient_id"]
        assert renamed["patient_id"].to_list() == ["P001", "P002", "P003,P003b"]

    def test_rename_columns_duplicate_targets_all_empty_gives_null(self, simple_synonyms: Path):
        """A merged group with nothing populated is null, not an empty string."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame({"Patient ID": [None, ""], "ID": ["", None]})

        renamed = mapper.rename_columns(df, sheet_name="Jan24")

        assert renamed["patient_id"].to_list() == [None, None]

    def test_rename_columns_merges_non_string_duplicate_targets(self, simple_synonyms: Path):
        """Merging casts to string, so numeric source columns do not raise."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame({"Age": [25, None], "Age*": [None, 30]})

        renamed = mapper.rename_columns(df, sheet_name="Jan24")

        assert renamed["age"].to_list() == ["25", "30"]

    def test_rename_columns_strict_mode_raises_error(self, simple_synonyms: Path):
        """Test that strict mode raises error for unmapped columns."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame(
            {
                "Age": [25],
                "UnknownColumn": ["value"],
            }
        )

        with pytest.raises(ValueError, match="Unmapped columns found"):
            mapper.rename_columns(df, strict=True)

    def test_rename_columns_no_changes_needed(self, simple_synonyms: Path):
        """Test renaming when columns are already standardized."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame(
            {
                "age": [25],
                "patient_id": ["P001"],
            }
        )

        renamed = mapper.rename_columns(df, sheet_name="Jan24")

        assert renamed.columns == df.columns
        assert renamed.equals(df)

    def test_get_expected_columns(self, simple_synonyms: Path):
        """Test getting set of expected standard columns."""
        mapper = ColumnMapper(simple_synonyms)

        expected = mapper.get_expected_columns()

        assert expected == {"age", "patient_id", "name", "province", "empty_column"}

    def test_get_missing_columns(self, simple_synonyms: Path):
        """Test getting missing columns from DataFrame."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame(
            {
                "age": [25],
                "patient_id": ["P001"],
            }
        )

        missing = mapper.get_missing_columns(df)

        assert missing == {"name", "province", "empty_column"}

    def test_validate_required_columns_success(self, simple_synonyms: Path):
        """Test validation passes when required columns present."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame(
            {
                "age": [25],
                "patient_id": ["P001"],
                "name": ["Test"],
            }
        )

        # Should not raise
        mapper.validate_required_columns(df, ["age", "patient_id"])

    def test_validate_required_columns_failure(self, simple_synonyms: Path):
        """Test validation fails when required columns missing."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame(
            {
                "age": [25],
            }
        )

        with pytest.raises(ValueError, match="Required columns missing"):
            mapper.validate_required_columns(df, ["age", "patient_id", "name"])


class TestLoaderFunctions:
    """Tests for loader convenience functions."""

    def test_load_patient_mapper_with_actual_file(self):
        """Test loading patient mapper with actual reference_data file."""
        mapper = load_patient_mapper()

        # Check that some expected columns are present
        assert "age" in mapper.synonyms
        assert "patient_id" in mapper.synonyms
        assert "province" in mapper.synonyms

        # Check that synonyms are loaded
        assert len(mapper._lookup) > 0
        assert mapper.get_standard_name("Age") == "age"

    def test_load_product_mapper_with_actual_file(self):
        """Test loading product mapper with actual reference_data file."""
        mapper = load_product_mapper()

        # Check that some expected columns are present
        assert "product" in mapper.synonyms
        assert "clinic_id" in mapper.synonyms

        # Check that synonyms are loaded
        assert len(mapper._lookup) > 0


class TestIntegrationWithActualData:
    """Integration tests with actual reference_data files."""

    def test_patient_mapper_renames_all_known_synonyms(self):
        """Test that patient mapper can rename all synonyms in YAML."""
        mapper = load_patient_mapper()

        # Create DataFrame with various synonyms
        test_data = {
            "Age": [25],
            "Patient ID": ["P001"],
            "D.O.B.": ["1999-01-01"],
            "Gender": ["M"],
        }

        df = pl.DataFrame(test_data)
        renamed = mapper.rename_columns(df, sheet_name="Jan24")

        # Check that columns are renamed correctly
        assert "age" in renamed.columns
        assert "patient_id" in renamed.columns
        assert "dob" in renamed.columns
        assert "sex" in renamed.columns

    def test_product_mapper_renames_all_known_synonyms(self):
        """Test that product mapper can rename all synonyms in YAML."""
        mapper = load_product_mapper()

        # Create DataFrame with various synonyms
        test_data = {
            "Product": ["Insulin"],
            "Date": ["2024-01-01"],
            "Units Received": [10],
        }

        df = pl.DataFrame(test_data)
        renamed = mapper.rename_columns(df, sheet_name="Jan24")

        # Check that columns are renamed correctly
        assert "product" in renamed.columns
        assert "product_entry_date" in renamed.columns
        assert "product_units_received" in renamed.columns
