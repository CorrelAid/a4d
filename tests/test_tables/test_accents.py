"""Tests for the accent-free name columns."""

import polars as pl

from a4d.tables.accents import add_ascii_columns, fold_accents


def test_fold_accents_removes_accents_and_keeps_case_and_spaces():
    assert fold_accents("Takéo") == "Takeo"
    assert fold_accents("Hà Nội") == "Ha Noi"
    assert fold_accents("Đà Nẵng") == "Da Nang"
    assert fold_accents("Bangkok") == "Bangkok"
    assert fold_accents(None) is None


def test_add_ascii_columns_keeps_the_official_name():
    df = pl.DataFrame(
        {
            "clinic_id": ["XX1", "XX2", "XX3"],
            "clinic_province": ["Takéo", "Hà Nội", None],
        }
    )

    result = add_ascii_columns(df, ["clinic_province"])

    assert result["clinic_province"].to_list() == ["Takéo", "Hà Nội", None]
    assert result["clinic_province_ascii"].to_list() == ["Takeo", "Ha Noi", None]


def test_add_ascii_columns_without_the_column_changes_nothing():
    df = pl.DataFrame({"clinic_id": ["XX1"]})

    assert add_ascii_columns(df, ["clinic_province"]).columns == ["clinic_id"]
