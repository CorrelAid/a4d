"""Tests for type conversion with error tracking."""

import polars as pl

from a4d.clean.converters import (
    correct_decimal_sign,
    cut_numeric_value,
    safe_convert_column,
    safe_convert_multiple_columns,
)
from a4d.config import settings
from a4d.errors import ErrorCollector


def test_safe_convert_column_success():
    """Test successful conversion without errors."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "age": ["25", "30", "18"],
        }
    )

    collector = ErrorCollector()

    result = safe_convert_column(
        df=df,
        column="age",
        target_type=pl.Int32,
        error_collector=collector,
    )

    assert result.schema["age"] == pl.Int32
    assert result["age"].to_list() == [25, 30, 18]
    assert len(collector) == 0  # No errors


def test_safe_convert_column_with_failures():
    """Test conversion with some failures."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 4,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003", "XX_QA004"],
            "age": ["25", "invalid", "30", "abc"],
        }
    )

    collector = ErrorCollector()

    result = safe_convert_column(
        df=df,
        column="age",
        target_type=pl.Int32,
        error_collector=collector,
    )

    assert result.schema["age"] == pl.Int32
    assert result["age"].to_list() == [
        25,
        int(settings.error_val_numeric),
        30,
        int(settings.error_val_numeric),
    ]
    assert len(collector) == 2  # Two failures

    # Check error details
    errors_df = collector.to_dataframe()
    assert errors_df.filter(pl.col("patient_id") == "XX_QA002")["original_value"][0] == "invalid"
    assert errors_df.filter(pl.col("patient_id") == "XX_QA004")["original_value"][0] == "abc"
    assert all(errors_df["error_code"] == "type_conversion")


def test_safe_convert_column_preserves_nulls():
    """Test that existing nulls are preserved."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "age": ["25", None, "30"],
        }
    )

    collector = ErrorCollector()

    result = safe_convert_column(
        df=df,
        column="age",
        target_type=pl.Int32,
        error_collector=collector,
    )

    assert result["age"].to_list() == [25, None, 30]
    assert len(collector) == 0  # Nulls are not errors


def test_correct_decimal_sign():
    """Test decimal sign correction."""
    df = pl.DataFrame(
        {
            "weight": ["70,5", "80,2", "65.5"],
        }
    )

    result = correct_decimal_sign(df, "weight")

    assert result["weight"].to_list() == ["70.5", "80.2", "65.5"]


def test_cut_numeric_value():
    """Test cutting out-of-range values."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 5,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003", "XX_QA004", "XX_QA005"],
            "age": [15, -5, 20, 30, 18],
        }
    )

    collector = ErrorCollector()

    result = cut_numeric_value(
        df=df,
        column="age",
        min_val=0,
        max_val=25,
        error_collector=collector,
    )

    assert result["age"].to_list() == [
        15,
        settings.error_val_numeric,  # -5 replaced
        20,
        settings.error_val_numeric,  # 30 replaced
        18,
    ]
    assert len(collector) == 2  # Two values out of range


def test_safe_convert_multiple_columns():
    """Test batch conversion of multiple columns."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 2,
            "patient_id": ["XX_QA001", "XX_QA002"],
            "age": ["25", "30"],
            "height": ["1.75", "1.80"],
            "weight": ["70", "80"],
        }
    )

    collector = ErrorCollector()

    result = safe_convert_multiple_columns(
        df=df,
        columns=["age", "height", "weight"],
        target_type=pl.Float64,
        error_collector=collector,
    )

    assert result.schema["age"] == pl.Float64
    assert result.schema["height"] == pl.Float64
    assert result.schema["weight"] == pl.Float64
    assert len(collector) == 0


def test_safe_convert_column_missing_column():
    """Test that missing columns are handled gracefully."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "patient_id": ["XX_QA001"],
        }
    )

    collector = ErrorCollector()

    # Should not raise error
    result = safe_convert_column(
        df=df,
        column="nonexistent",
        target_type=pl.Int32,
        error_collector=collector,
    )

    assert result.equals(df)
    assert len(collector) == 0


def test_safe_convert_column_float64():
    """Test conversion to Float64 with decimal values."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "weight": ["70.5", "not_a_number", "85.2"],
        }
    )

    collector = ErrorCollector()

    result = safe_convert_column(
        df=df,
        column="weight",
        target_type=pl.Float64,
        error_collector=collector,
    )

    assert result.schema["weight"] == pl.Float64
    assert result["weight"][0] == 70.5
    assert result["weight"][1] == settings.error_val_numeric
    assert result["weight"][2] == 85.2
    assert len(collector) == 1


def test_safe_convert_column_custom_error_value():
    """Test using a custom error value."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 2,
            "patient_id": ["XX_QA001", "XX_QA002"],
            "age": ["25", "invalid"],
        }
    )

    collector = ErrorCollector()

    result = safe_convert_column(
        df=df,
        column="age",
        target_type=pl.Int32,
        error_collector=collector,
        error_value=-1,
    )

    assert result["age"].to_list() == [25, -1]
    assert len(collector) == 1


def test_safe_convert_column_string_type():
    """Test conversion to string type (always succeeds)."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 2,
            "patient_id": ["XX_QA001", "XX_QA002"],
            "value": [123, 456],
        }
    )

    collector = ErrorCollector()

    result = safe_convert_column(
        df=df,
        column="value",
        target_type=pl.Utf8,
        error_collector=collector,
    )

    assert result.schema["value"] == pl.Utf8
    assert result["value"].to_list() == ["123", "456"]
    assert len(collector) == 0


def test_correct_decimal_sign_missing_column():
    """Test decimal sign correction with missing column."""
    df = pl.DataFrame({"other": ["value"]})

    result = correct_decimal_sign(df, "nonexistent")

    assert result.equals(df)


def test_cut_numeric_value_missing_column():
    """Test cutting with missing column."""
    df = pl.DataFrame({"other": [1, 2, 3]})

    collector = ErrorCollector()

    result = cut_numeric_value(
        df=df,
        column="nonexistent",
        min_val=0,
        max_val=10,
        error_collector=collector,
    )

    assert result.equals(df)
    assert len(collector) == 0


def test_cut_numeric_value_with_nulls():
    """Test that nulls are preserved when cutting values."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 4,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003", "XX_QA004"],
            "age": [15, None, 30, 20],
        }
    )

    collector = ErrorCollector()

    result = cut_numeric_value(
        df=df,
        column="age",
        min_val=0,
        max_val=25,
        error_collector=collector,
    )

    assert result["age"].to_list() == [15, None, settings.error_val_numeric, 20]
    assert len(collector) == 1  # Only 30 is out of range


def test_cut_numeric_value_ignores_existing_errors():
    """Test that existing error values are not re-logged."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "age": [15.0, settings.error_val_numeric, 30.0],
        }
    )

    collector = ErrorCollector()

    result = cut_numeric_value(
        df=df,
        column="age",
        min_val=0,
        max_val=25,
        error_collector=collector,
    )

    # Only 30 should be logged, not the existing error value
    assert result["age"].to_list() == [15, settings.error_val_numeric, settings.error_val_numeric]
    assert len(collector) == 1
