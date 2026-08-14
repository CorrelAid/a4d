"""Tests for type conversion with error tracking."""

from datetime import date

import polars as pl

from a4d.clean.converters import (
    correct_decimal_sign,
    cut_numeric_value,
    normalize_excel_formula_errors,
    parse_date_column,
    safe_convert_column,
    safe_convert_multiple_columns,
)
from a4d.clean.date_parser import parse_date_flexible, rescue_date_typos
from a4d.config import settings
from a4d.errors import ErrorCollector


def test_safe_convert_column_success():
    """Test successful conversion without errors."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
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
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003", "XX_YY004"],
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
    assert errors_df.filter(pl.col("patient_id") == "XX_YY002")["original_value"][0] == "invalid"
    assert errors_df.filter(pl.col("patient_id") == "XX_YY004")["original_value"][0] == "abc"
    assert all(errors_df["error_code"] == "type_conversion")


def test_safe_convert_column_preserves_nulls():
    """Test that existing nulls are preserved."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
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


def test_normalize_excel_formula_errors_nulls_and_logs():
    """Excel formula-error strings become null and are logged (ticket 27).

    Extraction preserves the source cell's literal error text; cleaning is
    where it becomes null, so the raw layer stays a faithful capture.
    """
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
            "t1d_diagnosis_age": ["9", "#NUM!", "#DIV/0!"],
        }
    )

    collector = ErrorCollector()

    result = normalize_excel_formula_errors(df, collector)

    assert result["t1d_diagnosis_age"].to_list() == ["9", None, None]
    assert len(collector) == 2
    codes = {e.error_code for e in collector.errors}
    assert codes == {"source_formula_error"}
    originals = {e.original_value for e in collector.errors}
    assert originals == {"#NUM!", "#DIV/0!"}


def test_normalize_excel_formula_errors_leaves_clean_data_untouched():
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 2,
            "patient_id": ["XX_YY001", "XX_YY002"],
            "bmi": ["17.5", None],
        }
    )

    collector = ErrorCollector()

    result = normalize_excel_formula_errors(df, collector)

    assert result["bmi"].to_list() == ["17.5", None]
    assert len(collector) == 0


def test_normalize_excel_formula_errors_skips_non_string_columns():
    df = pl.DataFrame(
        {"product_table_year": [2024.0, 2024.0]},
        schema={"product_table_year": pl.Float64},
    )

    collector = ErrorCollector()

    result = normalize_excel_formula_errors(df, collector)

    assert result.equals(df)
    assert len(collector) == 0


def test_normalize_excel_formula_errors_uses_custom_id_column():
    """The product arm identifies rows by `product`, not `patient_id`."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "product": ["Insulin"],
            "product_balance": ["#REF!"],
        }
    )

    collector = ErrorCollector()

    result = normalize_excel_formula_errors(df, collector, patient_id_col="product")

    assert result["product_balance"].to_list() == [None]
    assert len(collector) == 1
    assert collector.errors[0].patient_id == "Insulin"


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
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003", "XX_YY004", "XX_YY005"],
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
            "patient_id": ["XX_YY001", "XX_YY002"],
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
            "patient_id": ["XX_YY001"],
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
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
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
            "patient_id": ["XX_YY001", "XX_YY002"],
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
            "patient_id": ["XX_YY001", "XX_YY002"],
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
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003", "XX_YY004"],
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
            "patient_id": ["XX_YY001", "XX_YY002", "XX_YY003"],
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


def test_rescue_date_typos_known_patterns():
    assert rescue_date_typos("23-Mach-20") == ("23-MAR-20", True)
    assert rescue_date_typos("15-N0v-2021") == ("15-NOV-2021", True)
    assert rescue_date_typos("10-0ct-2024") == ("10-OCT-2024", True)
    assert rescue_date_typos("01-N0vember-2021") == ("01-NOVEMBER-2021", True)


def test_rescue_date_typos_passthrough():
    assert rescue_date_typos("15-Mar-2024") == ("15-Mar-2024", False)
    # Word-boundary protects unrelated substrings.
    assert rescue_date_typos("CON0CTOR") == ("CON0CTOR", False)


def test_parse_date_column_rescues_typo_and_logs():
    df = pl.DataFrame(
        {
            "file_name": ["t.xlsx", "t.xlsx"],
            "patient_id": ["P1", "P2"],
            "entry_date": ["23-Mach-20", "15-Mar-2024"],
        }
    )
    collector = ErrorCollector()

    result = parse_date_column(df, "entry_date", collector)

    parsed = result["entry_date"].to_list()
    assert parsed[0] == date(2020, 3, 23)
    assert parsed[1] == date(2024, 3, 15)
    assert len(collector) == 1
    err = collector.errors[0]
    assert err.error_code == "typo_rescued"
    assert err.column == "entry_date"
    assert err.original_value == "23-Mach-20"
    assert err.patient_id == "P1"


def test_parse_date_column_logs_unparseable_dates():
    """Pin parse_date_column's existing observability for genuinely unparseable
    cells. R has a separate 'non_processed_dates' warning that fires on rows
    R cannot parse via its narrower harmoniser; Python's parse_date_flexible
    parses many of those rows successfully (e.g. "Mar 18" abbreviated formats)
    and only sentinels truly-unparseable ones — at which point this existing
    type_conversion log entry covers the equivalent signal with strictly
    better signal-to-noise. See cleaning_divergences.md §10.
    """
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx", "test.xlsx", "test.xlsx"],
            "patient_id": ["P1", "P2", "P3"],
            "entry_date": ["2024-03-15", "garbage_value_xyz", "2024-04-20"],
        },
        schema={
            "file_name": pl.String,
            "patient_id": pl.String,
            "entry_date": pl.String,
        },
    )
    collector = ErrorCollector()

    result = parse_date_column(df=df, column="entry_date", error_collector=collector)

    parsed = result["entry_date"].to_list()
    assert parsed[0] == date(2024, 3, 15)
    assert parsed[1] == date(9999, 9, 9)  # error_val_date sentinel
    assert parsed[2] == date(2024, 4, 20)

    assert len(collector) == 1
    err = collector.errors[0]
    assert err.error_code == "type_conversion"
    assert err.function_name == "parse_date_column"
    assert err.column == "entry_date"
    assert err.original_value == "garbage_value_xyz"
    assert err.patient_id == "P2"


def test_parse_date_flexible_month_with_four_digit_year_is_first_of_month():
    """ "Jun 2006" is a real recorded diagnosis date in 2017-era trackers.

    Without an explicit branch dateutil fills the missing day from *today*,
    which makes the pipeline's output depend on the day it runs. R's own
    harmoniser resolves the same cell to the first of the month.
    """
    assert parse_date_flexible("Jun 2006") == date(2006, 6, 1)
    assert parse_date_flexible("March 2011") == date(2011, 3, 1)


def test_parse_date_flexible_month_with_two_digit_year_still_first_of_month():
    """The pre-existing two-digit branch keeps its behaviour."""
    assert parse_date_flexible("Mar-18") == date(2018, 3, 1)


def test_parse_date_flexible_handles_full_month_names():
    """Full month names were truncated to nonsense ("March" -> "Marh") and
    sentinelled; these are the docstring's own examples, which never worked.
    """
    assert parse_date_flexible("January-20") == date(2020, 1, 1)
    assert parse_date_flexible("March 2011") == date(2011, 3, 1)
    assert parse_date_flexible("07 March 2015") == date(2015, 3, 7)
    assert parse_date_flexible("Sept-19") == date(2019, 9, 1)


def test_parse_date_flexible_recovers_a_date_followed_by_free_text():
    """Hospitalisation cells carry a clause after the date. The prefix
    fallback must reach the date without a bare month name completing itself
    from today's date.
    """
    assert parse_date_flexible("16-Nov-2019 due to DKA") == date(2019, 11, 16)
    assert parse_date_flexible("Jan-2020 due to poor glycaemic control") == date(2020, 1, 1)
    assert parse_date_flexible("May 2019, Dec 2019 DKA") == date(2019, 5, 1)


def test_parse_date_flexible_still_sentinels_genuine_garbage():
    assert parse_date_flexible("garbage_value_xyz") == date(9999, 9, 9)
    assert parse_date_flexible("NA") is None


def test_parse_date_flexible_treats_every_numeric_missing_marker_as_missing():
    """A date column's missing markers are the same ones the numeric path
    already normalizes (ticket 38). "-" and "N/A" reaching the sentinel meant
    the cleaned output claimed "a date was recorded but is invalid" for a cell
    that plainly recorded nothing.
    """
    for marker in ("-", ".", "N/A", "n/a", "NULL", "None", "  "):
        assert parse_date_flexible(marker) is None, marker


def test_parse_date_flexible_treats_written_absence_as_missing():
    """Clinicians write absence in words, not only as "NA" (ticket 38:
    "Nil" 510 rows, "Unknown" 481, "?" 130 across the real 254-tracker set).
    """
    for marker in ("Nil", "nil", "Nill", "Unknown", "unknwon", "uncertain", "?"):
        assert parse_date_flexible(marker) is None, marker


def test_parse_date_flexible_treats_template_placeholder_text_as_missing():
    """The tracker template's own instruction text leaks into data rows
    ("Insert Date", "NA or Hospitalisation Date") -- it is a blank cell that
    was never filled in, not a date that failed to parse.
    """
    for marker in ("Insert Date", "Insert Date or NA", "NA or Hospitalisation Date"):
        assert parse_date_flexible(marker) is None, marker


def test_parse_date_flexible_still_sentinels_a_recorded_but_unusable_value():
    """The widened missing set must not swallow the case the sentinel exists
    for: something was written, and it is not a date and not an absence.
    """
    assert parse_date_flexible("garbage_value_xyz") == date(9999, 9, 9)
    assert parse_date_flexible("She stay in Hospital") == date(9999, 9, 9)
