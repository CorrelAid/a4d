"""Tests for data transformation functions."""

import polars as pl
import pytest

from a4d.clean.transformers import (
    extract_regimen,
    str_to_lower,
    apply_transformation,
    correct_decimal_sign_multiple,
    fix_sex,
)


def test_extract_regimen_basal():
    """Test extraction of basal-bolus regimen."""
    df = pl.DataFrame(
        {
            "insulin_regimen": [
                "Basal-bolus",
                "basal bolus",
                "BASAL",
                "Some basal text",
            ]
        }
    )

    result = extract_regimen(df)

    # All should be standardized to "Basal-bolus (MDI)"
    assert all(v == "Basal-bolus (MDI)" for v in result["insulin_regimen"].to_list())


def test_extract_regimen_premixed():
    """Test extraction of premixed regimen."""
    df = pl.DataFrame(
        {
            "insulin_regimen": [
                "Premixed",
                "PREMIXED 30/70",
                "premixed bd",
            ]
        }
    )

    result = extract_regimen(df)

    assert all(v == "Premixed 30/70 BD" for v in result["insulin_regimen"].to_list())


def test_extract_regimen_self_mixed():
    """Test extraction of self-mixed regimen."""
    df = pl.DataFrame(
        {
            "insulin_regimen": [
                "Self-mixed",
                "SELF-MIXED BD",
                "self-mixed",  # Must have hyphen to match
            ]
        }
    )

    result = extract_regimen(df)

    assert all(v == "Self-mixed BD" for v in result["insulin_regimen"].to_list())


def test_extract_regimen_conventional():
    """Test extraction of conventional regimen."""
    df = pl.DataFrame(
        {
            "insulin_regimen": [
                "Conventional",
                "Modified CONVENTIONAL TID",
                "conventional tid",
            ]
        }
    )

    result = extract_regimen(df)

    assert all(v == "Modified conventional TID" for v in result["insulin_regimen"].to_list())


def test_extract_regimen_missing_column():
    """Test that missing column is handled gracefully."""
    df = pl.DataFrame({"other": ["value"]})

    result = extract_regimen(df)

    assert result.equals(df)


def test_extract_regimen_preserves_nulls():
    """Test that nulls are preserved."""
    df = pl.DataFrame(
        {
            "insulin_regimen": ["Basal-bolus", None, "Premixed"],
        }
    )

    result = extract_regimen(df)

    assert result["insulin_regimen"][0] == "Basal-bolus (MDI)"
    assert result["insulin_regimen"][1] is None
    assert result["insulin_regimen"][2] == "Premixed 30/70 BD"


def test_extract_regimen_no_match():
    """Test values that don't match any pattern."""
    df = pl.DataFrame(
        {
            "insulin_regimen": [
                "Unknown regimen",
                "Other",
            ]
        }
    )

    result = extract_regimen(df)

    # Values that don't match should be unchanged (lowercased)
    assert result["insulin_regimen"].to_list() == ["unknown regimen", "other"]


def test_str_to_lower():
    """Test string lowercasing."""
    df = pl.DataFrame(
        {
            "status": ["ACTIVE", "Inactive", "Transferred", "MixedCase"],
        }
    )

    result = str_to_lower(df, "status")

    assert result["status"].to_list() == ["active", "inactive", "transferred", "mixedcase"]


def test_str_to_lower_preserves_nulls():
    """Test that nulls are preserved."""
    df = pl.DataFrame(
        {
            "status": ["ACTIVE", None, "Inactive"],
        }
    )

    result = str_to_lower(df, "status")

    assert result["status"][0] == "active"
    assert result["status"][1] is None
    assert result["status"][2] == "inactive"


def test_str_to_lower_missing_column():
    """Test that missing column is handled gracefully."""
    df = pl.DataFrame({"other": ["VALUE"]})

    result = str_to_lower(df, "nonexistent")

    assert result.equals(df)


def test_apply_transformation_extract_regimen():
    """Test applying extract_regimen transformation."""
    df = pl.DataFrame(
        {
            "insulin_regimen": ["Basal-bolus", "Premixed"],
        }
    )

    result = apply_transformation(df, "insulin_regimen", "extract_regimen")

    assert result["insulin_regimen"].to_list() == ["Basal-bolus (MDI)", "Premixed 30/70 BD"]


def test_apply_transformation_str_to_lower():
    """Test applying str_to_lower transformation (both naming conventions)."""
    df = pl.DataFrame(
        {
            "status": ["ACTIVE", "INACTIVE"],
        }
    )

    # Test with R function name
    result = apply_transformation(df, "status", "stringr::str_to_lower")
    assert result["status"].to_list() == ["active", "inactive"]

    # Reset
    df = pl.DataFrame({"status": ["ACTIVE", "INACTIVE"]})

    # Test with Python function name
    result = apply_transformation(df, "status", "str_to_lower")
    assert result["status"].to_list() == ["active", "inactive"]


def test_apply_transformation_unknown_function():
    """Test that unknown function raises error."""
    df = pl.DataFrame({"column": ["value"]})

    with pytest.raises(ValueError, match="Unknown transformation function"):
        apply_transformation(df, "column", "unknown_function")


def test_correct_decimal_sign_multiple():
    """Test correcting decimal signs for multiple columns."""
    df = pl.DataFrame(
        {
            "weight": ["70,5", "80,2"],
            "height": ["1,75", "1,80"],
            "hba1c": ["7,2", "6,8"],
        }
    )

    result = correct_decimal_sign_multiple(df, ["weight", "height", "hba1c"])

    assert result["weight"].to_list() == ["70.5", "80.2"]
    assert result["height"].to_list() == ["1.75", "1.80"]
    assert result["hba1c"].to_list() == ["7.2", "6.8"]


def test_correct_decimal_sign_multiple_missing_columns():
    """Test that missing columns are handled gracefully."""
    df = pl.DataFrame(
        {
            "weight": ["70,5", "80,2"],
        }
    )

    # Should not raise error even though height and hba1c don't exist
    result = correct_decimal_sign_multiple(df, ["weight", "height", "hba1c"])

    assert result["weight"].to_list() == ["70.5", "80.2"]


def test_extract_regimen_order_matters():
    """Test that transformation order matches R behavior.

    In R, the transformations are applied in order, and each one
    replaces the entire value if it matches.
    """
    df = pl.DataFrame(
        {
            "insulin_regimen": [
                "basal premixed",  # Both patterns match
            ]
        }
    )

    result = extract_regimen(df)

    # "basal" is checked first in the code, so it should match that
    assert result["insulin_regimen"][0] == "Basal-bolus (MDI)"


def test_fix_sex_female_synonyms():
    """Test that female synonyms are mapped to 'F'."""
    df = pl.DataFrame(
        {
            "sex": [
                "Female",
                "FEMALE",
                "girl",
                "Woman",
                "fem",
                "Feminine",
                "f",
                "F",
            ]
        }
    )

    result = fix_sex(df)

    # All should be mapped to "F"
    assert all(v == "F" for v in result["sex"].to_list())


def test_fix_sex_male_synonyms():
    """Test that male synonyms are mapped to 'M'."""
    df = pl.DataFrame(
        {
            "sex": [
                "Male",
                "MALE",
                "boy",
                "Man",
                "masculine",
                "m",
                "M",
            ]
        }
    )

    result = fix_sex(df)

    # All should be mapped to "M"
    assert all(v == "M" for v in result["sex"].to_list())


def test_fix_sex_invalid_values():
    """Test that invalid values are set to 'Undefined'."""
    df = pl.DataFrame(
        {
            "sex": [
                "invalid",
                "unknown",
                "other",
                "X",
            ]
        }
    )

    result = fix_sex(df)

    # All should be set to "Undefined"
    assert all(v == "Undefined" for v in result["sex"].to_list())


def test_fix_sex_preserves_nulls():
    """Test that null and empty values are preserved as null."""
    df = pl.DataFrame(
        {
            "sex": ["Female", None, "", "Male"],
        }
    )

    result = fix_sex(df)

    assert result["sex"][0] == "F"
    assert result["sex"][1] is None
    assert result["sex"][2] is None
    assert result["sex"][3] == "M"


def test_fix_sex_case_insensitive():
    """Test that matching is case-insensitive."""
    df = pl.DataFrame(
        {
            "sex": [
                "FEMALE",
                "female",
                "Female",
                "FeMaLe",
                "MALE",
                "male",
                "Male",
                "MaLe",
            ]
        }
    )

    result = fix_sex(df)

    assert result["sex"].to_list() == ["F", "F", "F", "F", "M", "M", "M", "M"]


def test_fix_sex_missing_column():
    """Test that missing column is handled gracefully."""
    df = pl.DataFrame({"other": ["value"]})

    result = fix_sex(df)

    assert result.equals(df)


def test_fix_sex_matches_r_behavior():
    """Test that fix_sex matches R's fix_sex() function exactly.

    This test uses the exact values from R's function definition.
    """
    df = pl.DataFrame(
        {
            "sex": [
                # Female synonyms from R
                "female", "girl", "woman", "fem", "feminine", "f",
                # Male synonyms from R
                "male", "boy", "man", "masculine", "m",
                # Invalid
                "other", "unknown",
                # Null/empty
                None, "",
            ]
        }
    )

    result = fix_sex(df)

    expected = ["F", "F", "F", "F", "F", "F", "M", "M", "M", "M", "M", "Undefined", "Undefined", None, None]
    assert result["sex"].to_list() == expected
