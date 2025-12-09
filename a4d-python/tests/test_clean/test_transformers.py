"""Tests for data transformation functions."""

import polars as pl
import pytest

from a4d.clean.transformers import (
    apply_transformation,
    correct_decimal_sign_multiple,
    extract_regimen,
    fix_bmi,
    fix_sex,
    fix_testing_frequency,
    replace_range_with_mean,
    split_bp_in_sys_and_dias,
    str_to_lower,
)
from a4d.config import settings


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
                "female",
                "girl",
                "woman",
                "fem",
                "feminine",
                "f",
                # Male synonyms from R
                "male",
                "boy",
                "man",
                "masculine",
                "m",
                # Invalid
                "other",
                "unknown",
                # Null/empty
                None,
                "",
            ]
        }
    )

    result = fix_sex(df)

    expected = [
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "M",
        "M",
        "M",
        "M",
        "M",
        "Undefined",
        "Undefined",
        None,
        None,
    ]
    assert result["sex"].to_list() == expected


def test_fix_bmi_basic_calculation():
    """Test basic BMI calculation from weight and height."""
    df = pl.DataFrame(
        {
            "weight": [70.0, 80.0, 65.0],
            "height": [1.75, 1.80, 1.60],
        }
    )

    result = fix_bmi(df)

    # BMI = weight / height^2
    assert "bmi" in result.columns
    assert result["bmi"][0] == pytest.approx(22.857, abs=0.001)  # 70 / 1.75^2 = 22.857
    assert result["bmi"][1] == pytest.approx(24.691, abs=0.001)  # 80 / 1.80^2 = 24.691
    assert result["bmi"][2] == pytest.approx(25.391, abs=0.001)  # 65 / 1.60^2 = 25.391


def test_fix_bmi_replaces_existing():
    """Test that calculated BMI replaces existing BMI value."""
    df = pl.DataFrame(
        {
            "weight": [70.0],
            "height": [1.75],
            "bmi": [999.9],  # Wrong BMI that should be replaced
        }
    )

    result = fix_bmi(df)

    # Should replace wrong BMI with correct calculation
    assert result["bmi"][0] == pytest.approx(22.857, abs=0.001)


def test_fix_bmi_null_weight():
    """Test that null weight results in null BMI."""
    df = pl.DataFrame(
        {
            "weight": [None, 70.0],
            "height": [1.75, 1.75],
        }
    )

    result = fix_bmi(df)

    assert result["bmi"][0] is None
    assert result["bmi"][1] is not None


def test_fix_bmi_null_height():
    """Test that null height results in null BMI."""
    df = pl.DataFrame(
        {
            "weight": [70.0, 70.0],
            "height": [None, 1.75],
        }
    )

    result = fix_bmi(df)

    assert result["bmi"][0] is None
    assert result["bmi"][1] is not None


def test_fix_bmi_error_value_weight():
    """Test that error value weight results in error value BMI."""
    df = pl.DataFrame(
        {
            "weight": [settings.error_val_numeric, 70.0],
            "height": [1.75, 1.75],
        }
    )

    result = fix_bmi(df)

    assert result["bmi"][0] == settings.error_val_numeric
    assert result["bmi"][1] == pytest.approx(22.857, abs=0.001)


def test_fix_bmi_error_value_height():
    """Test that error value height results in error value BMI."""
    df = pl.DataFrame(
        {
            "weight": [70.0, 70.0],
            "height": [settings.error_val_numeric, 1.75],
        }
    )

    result = fix_bmi(df)

    assert result["bmi"][0] == settings.error_val_numeric
    assert result["bmi"][1] == pytest.approx(22.857, abs=0.001)


def test_fix_bmi_missing_columns():
    """Test that missing weight or height columns are handled gracefully."""
    # Missing both
    df = pl.DataFrame({"other": [1, 2, 3]})
    result = fix_bmi(df)
    assert result.equals(df)

    # Missing weight
    df = pl.DataFrame({"height": [1.75, 1.80]})
    result = fix_bmi(df)
    assert result.equals(df)

    # Missing height
    df = pl.DataFrame({"weight": [70.0, 80.0]})
    result = fix_bmi(df)
    assert result.equals(df)


def test_fix_bmi_matches_r_behavior():
    """Test that fix_bmi matches R's fix_bmi() function exactly."""
    df = pl.DataFrame(
        {
            "weight": [70.0, None, settings.error_val_numeric, 80.0, 65.0],
            "height": [1.75, 1.80, 1.75, None, settings.error_val_numeric],
        }
    )

    result = fix_bmi(df)

    # Row 0: Normal calculation
    assert result["bmi"][0] == pytest.approx(22.857, abs=0.001)
    # Row 1: Null weight → null BMI
    assert result["bmi"][1] is None
    # Row 2: Error weight → error BMI
    assert result["bmi"][2] == settings.error_val_numeric
    # Row 3: Null height → null BMI
    assert result["bmi"][3] is None
    # Row 4: Error height → error BMI
    assert result["bmi"][4] == settings.error_val_numeric


# Tests for replace_range_with_mean


def test_replace_range_with_mean_basic():
    """Test basic range mean calculation."""
    assert replace_range_with_mean("0-2") == pytest.approx(1.0)
    assert replace_range_with_mean("2-3") == pytest.approx(2.5)
    assert replace_range_with_mean("1-5") == pytest.approx(3.0)


def test_replace_range_with_mean_larger_ranges():
    """Test larger range values."""
    assert replace_range_with_mean("10-20") == pytest.approx(15.0)
    assert replace_range_with_mean("0-10") == pytest.approx(5.0)


def test_replace_range_with_mean_same_values():
    """Test range where both values are the same."""
    assert replace_range_with_mean("0-0") == pytest.approx(0.0)
    assert replace_range_with_mean("5-5") == pytest.approx(5.0)


def test_replace_range_with_mean_decimals():
    """Test ranges with decimal values."""
    assert replace_range_with_mean("1.5-2.5") == pytest.approx(2.0)
    assert replace_range_with_mean("0.5-1.5") == pytest.approx(1.0)


# Tests for fix_testing_frequency


def test_fix_testing_frequency_passthrough():
    """Test that normal values pass through unchanged."""
    df = pl.DataFrame(
        {
            "patient_id": ["P1", "P2", "P3"],
            "testing_frequency": ["2", "1.5", "3"],
        }
    )

    result = fix_testing_frequency(df)

    assert result["testing_frequency"].to_list() == ["2", "1.5", "3"]


def test_fix_testing_frequency_range_replacement():
    """Test that ranges are replaced with mean."""
    df = pl.DataFrame(
        {
            "patient_id": ["P1", "P2", "P3"],
            "testing_frequency": ["0-2", "2-3", "1-5"],
        }
    )

    result = fix_testing_frequency(df)

    assert result["testing_frequency"].to_list() == ["1", "2.5", "3"]


def test_fix_testing_frequency_mixed():
    """Test mixed normal values and ranges."""
    df = pl.DataFrame(
        {
            "patient_id": ["P1", "P2", "P3", "P4"],
            "testing_frequency": ["2", "0-2", "1.5", "2-3"],
        }
    )

    result = fix_testing_frequency(df)

    assert result["testing_frequency"].to_list() == ["2", "1", "1.5", "2.5"]


def test_fix_testing_frequency_null_handling():
    """Test that null and empty values are preserved."""
    df = pl.DataFrame(
        {
            "patient_id": ["P1", "P2", "P3"],
            "testing_frequency": [None, "", "2"],
        }
    )

    result = fix_testing_frequency(df)

    assert result["testing_frequency"][0] is None
    assert result["testing_frequency"][1] is None
    assert result["testing_frequency"][2] == "2"


def test_fix_testing_frequency_whole_numbers():
    """Test that whole number means don't have decimal points."""
    df = pl.DataFrame(
        {
            "patient_id": ["P1", "P2"],
            "testing_frequency": ["0-2", "1-3"],
        }
    )

    result = fix_testing_frequency(df)

    # 0-2 mean is 1.0, should be "1" not "1.0"
    # 1-3 mean is 2.0, should be "2" not "2.0"
    assert result["testing_frequency"][0] == "1"
    assert result["testing_frequency"][1] == "2"


def test_fix_testing_frequency_missing_column():
    """Test that missing column is handled gracefully."""
    df = pl.DataFrame({"other": [1, 2, 3]})

    result = fix_testing_frequency(df)

    assert result.equals(df)


def test_fix_testing_frequency_large_range():
    """Test larger ranges."""
    df = pl.DataFrame(
        {
            "patient_id": ["P1"],
            "testing_frequency": ["0-10"],
        }
    )

    result = fix_testing_frequency(df)

    assert result["testing_frequency"][0] == "5"


def test_fix_testing_frequency_preserves_other_columns():
    """Test that other columns are preserved."""
    df = pl.DataFrame(
        {
            "patient_id": ["P1", "P2"],
            "testing_frequency": ["0-2", "3"],
            "other_col": ["A", "B"],
        }
    )

    result = fix_testing_frequency(df)

    assert "patient_id" in result.columns
    assert "other_col" in result.columns
    assert result["other_col"].to_list() == ["A", "B"]


# Tests for split_bp_in_sys_and_dias


def test_split_bp_valid_format():
    """Test splitting valid blood pressure format."""
    df = pl.DataFrame(
        {
            "blood_pressure_mmhg": ["96/55", "101/57", "120/80"],
        }
    )

    result = split_bp_in_sys_and_dias(df)

    assert "blood_pressure_sys_mmhg" in result.columns
    assert "blood_pressure_dias_mmhg" in result.columns
    assert "blood_pressure_mmhg" not in result.columns

    assert result["blood_pressure_sys_mmhg"].to_list() == ["96", "101", "120"]
    assert result["blood_pressure_dias_mmhg"].to_list() == ["55", "57", "80"]


def test_split_bp_invalid_no_slash():
    """Test that values without slash are replaced with error value."""
    df = pl.DataFrame(
        {
            "blood_pressure_mmhg": ["96", "1,6", ""],
        }
    )

    result = split_bp_in_sys_and_dias(df)

    error_val = str(int(settings.error_val_numeric))
    assert result["blood_pressure_sys_mmhg"].to_list() == [error_val, error_val, error_val]
    assert result["blood_pressure_dias_mmhg"].to_list() == [error_val, error_val, error_val]


def test_split_bp_mixed_valid_invalid():
    """Test mixed valid and invalid values."""
    df = pl.DataFrame(
        {
            "blood_pressure_mmhg": ["96/55", "invalid", "120/80"],
        }
    )

    result = split_bp_in_sys_and_dias(df)

    error_val = str(int(settings.error_val_numeric))
    assert result["blood_pressure_sys_mmhg"].to_list() == ["96", error_val, "120"]
    assert result["blood_pressure_dias_mmhg"].to_list() == ["55", error_val, "80"]


def test_split_bp_null_values():
    """Test that null values are preserved."""
    df = pl.DataFrame(
        {
            "blood_pressure_mmhg": ["96/55", None, "120/80"],
        }
    )

    result = split_bp_in_sys_and_dias(df)

    assert result["blood_pressure_sys_mmhg"][0] == "96"
    assert result["blood_pressure_sys_mmhg"][1] is None
    assert result["blood_pressure_sys_mmhg"][2] == "120"


def test_split_bp_missing_column():
    """Test that missing column is handled gracefully."""
    df = pl.DataFrame({"other": [1, 2, 3]})

    result = split_bp_in_sys_and_dias(df)

    assert result.equals(df)


def test_split_bp_drops_original_column():
    """Test that original blood_pressure_mmhg column is dropped."""
    df = pl.DataFrame(
        {
            "blood_pressure_mmhg": ["96/55", "120/80"],
        }
    )

    result = split_bp_in_sys_and_dias(df)

    assert "blood_pressure_mmhg" not in result.columns


def test_split_bp_preserves_other_columns():
    """Test that other columns are preserved."""
    df = pl.DataFrame(
        {
            "patient_id": ["P1", "P2"],
            "blood_pressure_mmhg": ["96/55", "120/80"],
            "other_col": ["A", "B"],
        }
    )

    result = split_bp_in_sys_and_dias(df)

    assert "patient_id" in result.columns
    assert "other_col" in result.columns
    assert result["patient_id"].to_list() == ["P1", "P2"]
    assert result["other_col"].to_list() == ["A", "B"]


def test_split_bp_multiple_invalid():
    """Test multiple invalid values log warning."""
    df = pl.DataFrame(
        {
            "blood_pressure_mmhg": ["invalid1", "invalid2", "96/55"],
        }
    )

    result = split_bp_in_sys_and_dias(df)

    error_val = str(int(settings.error_val_numeric))
    assert result["blood_pressure_sys_mmhg"][0] == error_val
    assert result["blood_pressure_sys_mmhg"][1] == error_val
    assert result["blood_pressure_sys_mmhg"][2] == "96"
