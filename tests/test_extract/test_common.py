"""Unit tests for shared tracker-level extraction helpers."""

from pathlib import Path

import polars as pl
import pytest

from a4d.extract.common import (
    clean_excel_errors,
    extract_tracker_month,
    find_month_sheets,
    get_tracker_year,
)


class _StubWorkbook:
    """Minimal stand-in for openpyxl.Workbook that exposes ``sheetnames``."""

    def __init__(self, sheetnames: list[str]):
        self.sheetnames = sheetnames


def test_get_tracker_year_from_sheet_names():
    year = get_tracker_year(Path("anything.xlsx"), ["Jan24", "Feb24", "Mar24"])
    assert year == 2024


def test_get_tracker_year_falls_back_to_filename():
    year = get_tracker_year(Path("2023_clinic_tracker.xlsx"), ["January", "February"])
    assert year == 2023


def test_get_tracker_year_raises_when_unparseable():
    with pytest.raises(ValueError):
        get_tracker_year(Path("clinic_tracker.xlsx"), ["January", "February"])


def test_find_month_sheets_filters_and_sorts():
    wb = _StubWorkbook(["Cover", "Mar24", "Jan24", "Feb24", "Notes"])
    sheets = find_month_sheets(wb)
    assert sheets == ["Jan24", "Feb24", "Mar24"]


def test_clean_excel_errors_replaces_with_null():
    df = pl.DataFrame(
        {"bmi": ["17.5", "#DIV/0!", "18.2", "#VALUE!"]},
        schema={"bmi": pl.String},
    )
    cleaned = clean_excel_errors(df)
    assert cleaned["bmi"].to_list() == ["17.5", None, "18.2", None]


def test_clean_excel_errors_skips_non_string_columns():
    df = pl.DataFrame(
        {"product_table_year": [2024.0, 2024.0]},
        schema={"product_table_year": pl.Float64},
    )
    cleaned = clean_excel_errors(df)
    assert cleaned.equals(df)


def test_extract_tracker_month_known_prefix():
    assert extract_tracker_month("Jan24") == 1
    assert extract_tracker_month("Dec23") == 12


def test_extract_tracker_month_unknown_prefix():
    with pytest.raises(ValueError):
        extract_tracker_month("Foo24")


def test_re_export_from_patient_module_still_works():
    """Backward-compat re-export shim stays callable from a4d.extract.patient."""
    from a4d.extract.patient import (
        clean_excel_errors as p_clean_excel_errors,
    )
    from a4d.extract.patient import (
        extract_tracker_month as p_extract_tracker_month,
    )
    from a4d.extract.patient import (
        find_month_sheets as p_find_month_sheets,
    )
    from a4d.extract.patient import (
        get_tracker_year as p_get_tracker_year,
    )

    assert p_clean_excel_errors is clean_excel_errors
    assert p_extract_tracker_month is extract_tracker_month
    assert p_find_month_sheets is find_month_sheets
    assert p_get_tracker_year is get_tracker_year
