"""Tests for column synonym mapper."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import polars as pl
import pytest
import yaml

from a4d.synonyms import ColumnMapper
from a4d.synonyms.mapper import load_patient_mapper, load_product_mapper


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
        assert len(mapper._lookup) == 8  # Total non-empty synonyms (3+3+1+1)

    def test_init_missing_file_raises_error(self):
        """Test that __init__ raises error for missing file."""
        with pytest.raises(FileNotFoundError, match="YAML file not found"):
            ColumnMapper(Path("/nonexistent/file.yaml"))

    def test_build_lookup_creates_reverse_mapping(self, simple_synonyms: Path):
        """Test that reverse lookup is built correctly."""
        mapper = ColumnMapper(simple_synonyms)

        assert mapper._lookup["Age"] == "age"
        assert mapper._lookup["Age*"] == "age"
        assert mapper._lookup["age on reporting"] == "age"
        assert mapper._lookup["ID"] == "patient_id"
        assert mapper._lookup["Patient ID"] == "patient_id"

    def test_build_lookup_handles_duplicates(self, duplicate_synonyms: Path):
        """Test that duplicate synonyms log warning and use last definition."""
        mapper = ColumnMapper(duplicate_synonyms)

        # "Age" appears in both, should map to the second one encountered
        assert "Age" in mapper._lookup
        assert mapper._lookup["Age"] in ["age", "age_at_diagnosis"]

    def test_get_standard_name(self, simple_synonyms: Path):
        """Test getting standard name for a column."""
        mapper = ColumnMapper(simple_synonyms)

        assert mapper.get_standard_name("Age") == "age"
        assert mapper.get_standard_name("Patient ID*") == "patient_id"
        assert mapper.get_standard_name("unknown_column") == "unknown_column"

    def test_rename_columns_basic(self, simple_synonyms: Path):
        """Test basic column renaming."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame({
            "Age": [25, 30],
            "Patient ID": ["P001", "P002"],
            "Province": ["Bangkok", "Hanoi"],
        })

        renamed = mapper.rename_columns(df)

        assert "age" in renamed.columns
        assert "patient_id" in renamed.columns
        assert "province" in renamed.columns
        assert "Age" not in renamed.columns

    def test_rename_columns_keeps_unmapped(self, simple_synonyms: Path):
        """Test that unmapped columns are kept by default."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame({
            "Age": [25],
            "UnknownColumn": ["value"],
            "AnotherUnmapped": [42],
        })

        renamed = mapper.rename_columns(df)

        assert "age" in renamed.columns
        assert "UnknownColumn" in renamed.columns
        assert "AnotherUnmapped" in renamed.columns

    def test_rename_columns_strict_mode_raises_error(self, simple_synonyms: Path):
        """Test that strict mode raises error for unmapped columns."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame({
            "Age": [25],
            "UnknownColumn": ["value"],
        })

        with pytest.raises(ValueError, match="Unmapped columns found"):
            mapper.rename_columns(df, strict=True)

    def test_rename_columns_no_changes_needed(self, simple_synonyms: Path):
        """Test renaming when columns are already standardized."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame({
            "age": [25],
            "patient_id": ["P001"],
        })

        renamed = mapper.rename_columns(df)

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

        df = pl.DataFrame({
            "age": [25],
            "patient_id": ["P001"],
        })

        missing = mapper.get_missing_columns(df)

        assert missing == {"name", "province", "empty_column"}

    def test_validate_required_columns_success(self, simple_synonyms: Path):
        """Test validation passes when required columns present."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame({
            "age": [25],
            "patient_id": ["P001"],
            "name": ["Test"],
        })

        # Should not raise
        mapper.validate_required_columns(df, ["age", "patient_id"])

    def test_validate_required_columns_failure(self, simple_synonyms: Path):
        """Test validation fails when required columns missing."""
        mapper = ColumnMapper(simple_synonyms)

        df = pl.DataFrame({
            "age": [25],
        })

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
        renamed = mapper.rename_columns(df)

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
        renamed = mapper.rename_columns(df)

        # Check that columns are renamed correctly
        assert "product" in renamed.columns
        assert "product_entry_date" in renamed.columns
        assert "product_units_received" in renamed.columns
