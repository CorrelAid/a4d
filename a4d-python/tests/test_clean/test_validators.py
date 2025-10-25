"""Tests for schema and validation utilities."""

import polars as pl
import pytest

from a4d.clean.validators import (
    load_validation_rules,
    validate_allowed_values,
    validate_column_from_rules,
    validate_all_columns,
)
from a4d.config import settings
from a4d.errors import ErrorCollector


def test_load_validation_rules():
    """Test loading validation rules from YAML."""
    rules = load_validation_rules()

    # Check that rules were loaded
    assert isinstance(rules, dict)
    assert len(rules) > 0

    # Check a specific column rule (new simplified structure)
    assert "status" in rules
    assert "allowed_values" in rules["status"]
    assert "replace_invalid" in rules["status"]
    assert isinstance(rules["status"]["allowed_values"], list)
    assert len(rules["status"]["allowed_values"]) > 0

    # Check another column
    assert "clinic_visit" in rules
    assert rules["clinic_visit"]["allowed_values"] == ["N", "Y"]
    assert rules["clinic_visit"]["replace_invalid"] is True


def test_validate_allowed_values_all_valid():
    """Test validation when all values are valid."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "status": ["Active", "Inactive", "Active"],
        }
    )

    collector = ErrorCollector()

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active", "Inactive", "Transferred"],
        error_collector=collector,
        replace_invalid=True,
    )

    assert result["status"].to_list() == ["Active", "Inactive", "Active"]
    assert len(collector) == 0


def test_validate_allowed_values_with_invalid():
    """Test validation when some values are invalid."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 4,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003", "XX_QA004"],
            "status": ["Active", "INVALID", "Inactive", "BAD_VALUE"],
        }
    )

    collector = ErrorCollector()

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active", "Inactive"],
        error_collector=collector,
        replace_invalid=True,
    )

    assert result["status"].to_list() == [
        "Active",
        settings.error_val_character,
        "Inactive",
        settings.error_val_character,
    ]
    assert len(collector) == 2

    # Check error details
    errors_df = collector.to_dataframe()
    assert errors_df.filter(pl.col("patient_id") == "XX_QA002")["original_value"][0] == "INVALID"
    assert errors_df.filter(pl.col("patient_id") == "XX_QA004")["original_value"][0] == "BAD_VALUE"


def test_validate_allowed_values_preserves_nulls():
    """Test that nulls are preserved and not logged as errors."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "status": ["Active", None, "Inactive"],
        }
    )

    collector = ErrorCollector()

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active", "Inactive"],
        error_collector=collector,
        replace_invalid=True,
    )

    assert result["status"].to_list() == ["Active", None, "Inactive"]
    assert len(collector) == 0


def test_validate_allowed_values_no_replace():
    """Test validation without replacing invalid values."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 2,
            "patient_id": ["XX_QA001", "XX_QA002"],
            "status": ["Active", "INVALID"],
        }
    )

    collector = ErrorCollector()

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active"],
        error_collector=collector,
        replace_invalid=False,
    )

    # Invalid value should NOT be replaced
    assert result["status"].to_list() == ["Active", "INVALID"]
    # But it should still be logged
    assert len(collector) == 1


def test_validate_allowed_values_missing_column():
    """Test that missing columns are handled gracefully."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "patient_id": ["XX_QA001"],
        }
    )

    collector = ErrorCollector()

    result = validate_allowed_values(
        df=df,
        column="nonexistent",
        allowed_values=["Active"],
        error_collector=collector,
    )

    assert result.equals(df)
    assert len(collector) == 0


def test_validate_allowed_values_ignores_existing_errors():
    """Test that existing error values are not re-logged."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "status": ["Active", settings.error_val_character, "INVALID"],
        }
    )

    collector = ErrorCollector()

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active", "Inactive"],
        error_collector=collector,
        replace_invalid=True,
    )

    # Only "INVALID" should be logged, not the existing error value
    assert len(collector) == 1
    assert result["status"].to_list() == [
        "Active",
        settings.error_val_character,
        settings.error_val_character,
    ]


def test_validate_column_from_rules():
    """Test validation using rules from data_cleaning.yaml."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "clinic_visit": ["Y", "N", "INVALID"],
        }
    )

    rules = load_validation_rules()
    collector = ErrorCollector()

    result = validate_column_from_rules(
        df=df,
        column="clinic_visit",
        rules=rules["clinic_visit"],
        error_collector=collector,
    )

    # "INVALID" should be replaced with error value
    assert result["clinic_visit"].to_list() == ["Y", "N", settings.error_val_character]
    assert len(collector) == 1


def test_validate_column_from_rules_missing_column():
    """Test validation with missing column."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "patient_id": ["XX_QA001"],
        }
    )

    rules = load_validation_rules()
    collector = ErrorCollector()

    result = validate_column_from_rules(
        df=df,
        column="nonexistent",
        rules=rules["clinic_visit"],
        error_collector=collector,
    )

    assert result.equals(df)
    assert len(collector) == 0


def test_validate_all_columns():
    """Test validation of all columns with rules.

    Note: Status values are lowercase because transformers.py lowercases them
    before validation. This test focuses on validation only.
    """
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "clinic_visit": ["Y", "N", "INVALID1"],
            "patient_consent": ["Y", "INVALID2", "N"],
            "status": ["active", "INVALID3", "inactive"],  # Lowercase (post-transformation)
        }
    )

    collector = ErrorCollector()

    result = validate_all_columns(df, collector)

    # All invalid values should be replaced
    assert result["clinic_visit"].to_list() == ["Y", "N", settings.error_val_character]
    assert result["patient_consent"].to_list() == ["Y", settings.error_val_character, "N"]
    assert result["status"].to_list() == ["active", settings.error_val_character, "inactive"]

    # Should have logged 3 errors (one per invalid value)
    assert len(collector) == 3


def test_validate_all_columns_only_validates_existing():
    """Test that validation only processes columns that exist in DataFrame."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "patient_id": ["XX_QA001"],
            "clinic_visit": ["Y"],
            # Many other columns from rules don't exist
        }
    )

    collector = ErrorCollector()

    # Should not raise error even though many rule columns don't exist
    result = validate_all_columns(df, collector)

    assert "clinic_visit" in result.columns
    assert len(collector) == 0


def test_validate_allowed_values_case_sensitive():
    """Test that validation is case-sensitive."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "clinic_visit": ["Y", "y", "N"],
        }
    )

    collector = ErrorCollector()

    result = validate_allowed_values(
        df=df,
        column="clinic_visit",
        allowed_values=["Y", "N"],
        error_collector=collector,
        replace_invalid=True,
    )

    # Lowercase "y" should be invalid
    assert result["clinic_visit"].to_list() == ["Y", settings.error_val_character, "N"]
    assert len(collector) == 1
