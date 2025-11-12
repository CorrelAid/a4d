"""Tests for schema and validation utilities."""

import polars as pl
import pytest

from a4d.clean.validators import (
    load_validation_rules,
    validate_allowed_values,
    validate_column_from_rules,
    validate_all_columns,
    fix_patient_id,
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
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
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
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003", "XX_YY004"],
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
    # Note: file_name and patient_id are "unknown" placeholders in validate_allowed_values
    # They get filled in during bulk processing operations
    errors_df = collector.to_dataframe()
    # Order is not guaranteed, so check using sets
    assert set(errors_df["original_value"].to_list()) == {"INVALID", "BAD_VALUE"}
    assert errors_df["column"].to_list() == ["status", "status"]
    assert errors_df["error_code"].to_list() == ["invalid_value", "invalid_value"]


def test_validate_allowed_values_preserves_nulls():
    """Test that nulls are preserved and not logged as errors."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
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
            "patient_id": ["XX_YY001", "XX_YY002"],
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
            "patient_id": ["XX_YY001"],
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
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
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
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
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
            "patient_id": ["XX_YY001"],
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

    Note: Validation uses case-insensitive matching and normalizes to canonical values.
    For example, "active" becomes "Active", "y" becomes "Y".
    """
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
            "clinic_visit": ["Y", "N", "INVALID1"],
            "patient_consent": ["Y", "INVALID2", "N"],
            "status": ["active", "INVALID3", "inactive"],  # Lowercase input
        }
    )

    collector = ErrorCollector()

    result = validate_all_columns(df, collector)

    # All invalid values should be replaced
    # Valid values should be normalized to canonical form (Title Case for status)
    assert result["clinic_visit"].to_list() == ["Y", "N", settings.error_val_character]
    assert result["patient_consent"].to_list() == ["Y", settings.error_val_character, "N"]
    assert result["status"].to_list() == ["Active", settings.error_val_character, "Inactive"]

    # Should have logged 3 errors (one per invalid value)
    assert len(collector) == 3


def test_validate_all_columns_only_validates_existing():
    """Test that validation only processes columns that exist in DataFrame."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "patient_id": ["XX_YY001"],
            "clinic_visit": ["Y"],
            # Many other columns from rules don't exist
        }
    )

    collector = ErrorCollector()

    # Should not raise error even though many rule columns don't exist
    result = validate_all_columns(df, collector)

    assert "clinic_visit" in result.columns
    assert len(collector) == 0


def test_validate_allowed_values_case_insensitive():
    """Test that validation is case-insensitive and normalizes to canonical values.

    Validation matches R behavior:
    - "y" matches "Y" (case-insensitive)
    - Returns canonical value "Y" (not the input "y")
    """
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
            "clinic_visit": ["Y", "y", "N"],  # Mixed case
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

    # Lowercase "y" should match "Y" and be normalized to canonical "Y"
    assert result["clinic_visit"].to_list() == ["Y", "Y", "N"]
    assert len(collector) == 0  # No errors - "y" is valid


# Tests for fix_patient_id


def test_fix_patient_id_valid_ids():
    """Test that valid patient IDs are not changed."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_EW004", "AB_CD123", "XY_ZW999"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"].to_list() == ["KD_EW004", "AB_CD123", "XY_ZW999"]
    assert len(collector) == 0


def test_fix_patient_id_hyphen_normalization():
    """Test that hyphens are replaced with underscores."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD-EW004", "AB-CD123"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"].to_list() == ["KD_EW004", "AB_CD123"]
    assert len(collector) == 0  # Normalization doesn't generate errors


def test_fix_patient_id_truncation():
    """Test that IDs > 8 chars are truncated."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_EW004XY", "KD_EW004ABC", "VERYLONGID"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    # First 8 characters
    assert result["patient_id"].to_list() == ["KD_EW004", "KD_EW004", "VERYLONG"]
    # Truncation generates warnings
    assert len(collector) == 3


def test_fix_patient_id_invalid_too_short_first_part():
    """Test that IDs with < 2 letters in first part are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["K_EW004", "A_CD123"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined"]
    assert len(collector) == 2


def test_fix_patient_id_invalid_too_short_second_part():
    """Test that IDs with < 2 letters in second part are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_E004", "AB_C123"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined"]
    assert len(collector) == 2


def test_fix_patient_id_invalid_wrong_digits():
    """Test that IDs without exactly 3 digits are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_EW04", "KD_EW0", "KD_EW0001"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    # All invalid (2 digits, 1 digit, 4 digits)
    assert result["patient_id"][0] == "Undefined"
    assert result["patient_id"][1] == "Undefined"
    # KD_EW0001 is > 8 chars, so truncated to KD_EW000
    assert result["patient_id"][2] == "KD_EW000"


def test_fix_patient_id_invalid_digits_in_letter_positions():
    """Test that IDs with digits instead of letters are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["11_EW004", "KD_E1004", "12_34567"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined", "Undefined"]
    assert len(collector) == 3


def test_fix_patient_id_invalid_letters_in_digit_positions():
    """Test that IDs with letters in digit positions are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_EWX04", "KD_EWABC"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined"]
    assert len(collector) == 2


def test_fix_patient_id_invalid_no_underscore():
    """Test that IDs without underscore are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["KDEW004", "INVALID"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined"]
    assert len(collector) == 2


def test_fix_patient_id_null_values():
    """Test that null values are preserved."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_EW004", None, "AB_CD123"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"][0] == "KD_EW004"
    assert result["patient_id"][1] is None
    assert result["patient_id"][2] == "AB_CD123"
    assert len(collector) == 0


def test_fix_patient_id_empty_string():
    """Test that empty string is replaced with error value."""
    df = pl.DataFrame(
        {
            "patient_id": ["", "KD_EW004"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"][0] == "Undefined"
    assert result["patient_id"][1] == "KD_EW004"
    assert len(collector) == 1


def test_fix_patient_id_missing_column():
    """Test that missing column is handled gracefully."""
    df = pl.DataFrame({"other": [1, 2, 3]})

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result.equals(df)
    assert len(collector) == 0


def test_fix_patient_id_mixed_valid_invalid():
    """Test mixed valid and invalid IDs."""
    df = pl.DataFrame(
        {
            "patient_id": [
                "KD_EW004",  # Valid
                "KD-AB123",  # Valid after normalization
                "INVALID",  # Invalid, replaced
                "KD_EW004XY",  # Invalid, truncated
                None,  # Null preserved
            ],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    assert result["patient_id"][0] == "KD_EW004"
    assert result["patient_id"][1] == "KD_AB123"
    assert result["patient_id"][2] == "Undefined"
    assert result["patient_id"][3] == "KD_EW004"
    assert result["patient_id"][4] is None
    assert len(collector) == 2  # 1 replacement + 1 truncation


def test_fix_patient_id_lowercase_letters():
    """Test that lowercase letters make ID invalid."""
    df = pl.DataFrame(
        {
            "patient_id": ["kd_ew004", "KD_ew004", "kd_EW004"],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    # All should be replaced (format requires uppercase)
    assert result["patient_id"].to_list() == ["Undefined", "Undefined", "Undefined"]
    assert len(collector) == 3


def test_fix_patient_id_matches_r_behavior():
    """Test that fix_patient_id matches R's fix_id() exactly."""
    df = pl.DataFrame(
        {
            "patient_id": [
                "KD_EW004",  # Valid
                "KD-EW004",  # Normalize - to _
                "K_EW004",  # Too short first part
                "KD_E004",  # Too short second part
                "KD_EWX04",  # Invalid format
                "11_EW004",  # Digits instead of letters
                "KD_E1004",  # Digit in letter position
                "KD_EW004XY",  # Truncate (> 8 chars)
                None,  # Null
                "",  # Empty
            ],
        }
    )

    collector = ErrorCollector()
    result = fix_patient_id(df, collector)

    expected = [
        "KD_EW004",  # Valid
        "KD_EW004",  # Normalized
        "Undefined",  # Invalid
        "Undefined",  # Invalid
        "Undefined",  # Invalid
        "Undefined",  # Invalid
        "Undefined",  # Invalid
        "KD_EW004",  # Truncated
        None,  # Null
        "Undefined",  # Empty → Other
    ]
    assert result["patient_id"].to_list() == expected
    # Errors: 5 replacements + 1 truncation + 1 empty string = 7
    assert len(collector) == 7
