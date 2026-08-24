"""Unit tests for shared tracker-level extraction helpers."""

from pathlib import Path

import polars as pl
import pytest

from a4d.extract.common import (
    extract_tracker_month,
    find_month_sheets,
    get_tracker_year,
    normalize_patient_id_expr,
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
    with pytest.raises(ValueError, match="Could not determine year"):
        get_tracker_year(Path("clinic_tracker.xlsx"), ["January", "February"])


def test_find_month_sheets_filters_and_sorts():
    wb = _StubWorkbook(["Cover", "Mar24", "Jan24", "Feb24", "Notes"])
    sheets = find_month_sheets(wb)
    assert sheets == ["Jan24", "Feb24", "Mar24"]


def test_extract_tracker_month_known_prefix():
    assert extract_tracker_month("Jan24") == 1
    assert extract_tracker_month("Dec23") == 12


def test_extract_tracker_month_unknown_prefix():
    with pytest.raises(ValueError, match="Could not extract month"):
        extract_tracker_month("Foo24")


def test_re_export_from_patient_module_still_works():
    """Backward-compat re-export shim stays callable from a4d.extract.patient."""
    from a4d.extract.patient import (
        extract_tracker_month as p_extract_tracker_month,
    )
    from a4d.extract.patient import (
        find_month_sheets as p_find_month_sheets,
    )
    from a4d.extract.patient import (
        get_tracker_year as p_get_tracker_year,
    )

    assert p_extract_tracker_month is extract_tracker_month
    assert p_find_month_sheets is find_month_sheets
    assert p_get_tracker_year is get_tracker_year


def _normalize(ids: list[str | None]) -> list[str | None]:
    return (
        pl.DataFrame({"patient_id": ids}, schema={"patient_id": pl.Utf8})
        .select(normalize_patient_id_expr(pl.col("patient_id")).alias("k"))["k"]
        .to_list()
    )


def test_normalize_patient_id_folds_hyphen_to_underscore():
    """The Mahosot case: month sheets write LA-MH056, the Patient List LA_MH056."""
    assert _normalize(["LA-MH056", "LA_MH056"]) == ["LA_MH056", "LA_MH056"]


def test_normalize_patient_id_strips_transfer_clinic_suffix():
    assert _normalize(["MY_SM003_SB", "LA-MH093_LF"]) == ["MY_SM003", "LA_MH093"]


def test_normalize_patient_id_leaves_well_formed_ids_alone():
    assert _normalize(["KH_NP026", "TH_ST029"]) == ["KH_NP026", "TH_ST029"]


def test_normalize_patient_id_passes_through_ids_without_separator():
    """An ID with no underscore has no country/clinic split to extract."""
    assert _normalize(["ABC123", ""]) == ["ABC123", ""]


def test_normalize_patient_id_preserves_null():
    assert _normalize([None, "LA-MH056"]) == [None, "LA_MH056"]
