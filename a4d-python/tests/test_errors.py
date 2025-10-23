"""Tests for error tracking functionality."""

import polars as pl

from a4d.errors import DataError, ErrorCollector


def test_data_error_creation():
    """Test creating a DataError instance."""
    error = DataError(
        file_name="test.xlsx",
        patient_id="XX_YY001",
        column="age",
        original_value="invalid",
        error_message="Could not convert to Int32",
        error_code="type_conversion",
        function_name="safe_convert_column",
    )

    assert error.file_name == "test.xlsx"
    assert error.patient_id == "XX_YY001"
    assert error.column == "age"
    assert error.error_code == "type_conversion"
    assert error.script == "clean"  # default value


def test_error_collector_add_error():
    """Test adding errors to collector."""
    collector = ErrorCollector()

    assert len(collector) == 0
    assert not collector  # __bool__ returns False when empty

    collector.add_error(
        file_name="test.xlsx",
        patient_id="XX_YY001",
        column="age",
        original_value="invalid",
        error_message="Could not convert",
        error_code="type_conversion",
    )

    assert len(collector) == 1
    assert collector  # __bool__ returns True when has errors


def test_error_collector_add_errors():
    """Test adding multiple errors at once."""
    collector = ErrorCollector()

    errors = [
        DataError(
            file_name="test.xlsx",
            patient_id="XX_YY001",
            column="age",
            original_value="invalid",
            error_message="Could not convert",
            error_code="type_conversion",
        ),
        DataError(
            file_name="test.xlsx",
            patient_id="XX_YY002",
            column="weight",
            original_value="abc",
            error_message="Could not convert",
            error_code="type_conversion",
        ),
    ]

    collector.add_errors(errors)

    assert len(collector) == 2


def test_error_collector_to_dataframe():
    """Test converting errors to DataFrame."""
    collector = ErrorCollector()

    collector.add_error(
        file_name="test.xlsx",
        patient_id="XX_YY001",
        column="age",
        original_value="invalid",
        error_message="Could not convert to Int32",
        error_code="type_conversion",
        function_name="safe_convert_column",
    )

    df = collector.to_dataframe()

    assert isinstance(df, pl.DataFrame)
    assert len(df) == 1
    assert "file_name" in df.columns
    assert "patient_id" in df.columns
    assert "column" in df.columns
    assert "error_code" in df.columns

    # Check categorical columns
    assert df.schema["error_code"] == pl.Categorical
    assert df.schema["script"] == pl.Categorical


def test_error_collector_to_dataframe_empty():
    """Test converting empty collector to DataFrame."""
    collector = ErrorCollector()
    df = collector.to_dataframe()

    assert isinstance(df, pl.DataFrame)
    assert len(df) == 0
    # Should still have correct schema
    assert "file_name" in df.columns
    assert "error_code" in df.columns


def test_error_collector_get_summary():
    """Test error summary by error_code."""
    collector = ErrorCollector()

    collector.add_error(
        file_name="test.xlsx",
        patient_id="XX_YY001",
        column="age",
        original_value="invalid",
        error_message="Type error",
        error_code="type_conversion",
    )
    collector.add_error(
        file_name="test.xlsx",
        patient_id="XX_YY002",
        column="age",
        original_value="999",
        error_message="Out of range",
        error_code="invalid_value",
    )
    collector.add_error(
        file_name="test.xlsx",
        patient_id="XX_YY003",
        column="weight",
        original_value="abc",
        error_message="Type error",
        error_code="type_conversion",
    )

    summary = collector.get_error_summary()

    assert summary == {"type_conversion": 2, "invalid_value": 1}


def test_error_collector_clear():
    """Test clearing errors from collector."""
    collector = ErrorCollector()

    collector.add_error(
        file_name="test.xlsx",
        patient_id="XX_YY001",
        column="age",
        original_value="invalid",
        error_message="Error",
        error_code="type_conversion",
    )

    assert len(collector) == 1

    collector.clear()

    assert len(collector) == 0
    assert not collector
