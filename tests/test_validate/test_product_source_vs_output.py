"""Tests for source_vs_output_product."""

from __future__ import annotations

import polars as pl

from a4d.errors import ErrorCollector
from a4d.validate.source_vs_output_product import (
    _explode_multi_product_cells,
    check_column_null_rate_delta,
    check_missing_groups,
    check_row_count_delta,
)

RAW_SCHEMA = {
    "file_name": pl.Utf8,
    "product_sheet_name": pl.Utf8,
    "product": pl.Utf8,
    "product_units_received": pl.Utf8,
    "product_units_released": pl.Utf8,
}

CLEAN_SCHEMA = {
    "file_name": pl.Utf8,
    "product_sheet_name": pl.Utf8,
    "product": pl.Utf8,
    "product_units_received": pl.Float64,
    "product_units_released": pl.Float64,
    "product_balance_status": pl.Utf8,
}


def _raw(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=RAW_SCHEMA)


def _clean(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=CLEAN_SCHEMA)


def test_explode_splits_multi_product_cell() -> None:
    df = _raw(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A; Insulin B",
                "product_units_received": "10",
                "product_units_released": None,
            }
        ]
    )
    exploded = _explode_multi_product_cells(df)
    assert sorted(exploded["product"].to_list()) == ["Insulin A", "Insulin B"]


def test_missing_group_after_explode() -> None:
    raw = _raw(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A; Insulin B",
                "product_units_received": "10",
                "product_units_released": None,
            }
        ]
    )
    cleaned = _clean(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A",
                "product_units_received": 10.0,
                "product_units_released": None,
                "product_balance_status": "start",
            }
            # Insulin B is missing from cleaned -> should fire MISSING_GROUP
        ]
    )
    coll = ErrorCollector()
    check_missing_groups(_explode_multi_product_cells(raw), cleaned, coll)
    msgs = [e.error_message for e in coll.errors]
    assert any("MISSING_GROUP" in m and "Insulin B" in m for m in msgs)


def test_phantom_group_fires_for_invented_product() -> None:
    raw = _raw(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A",
                "product_units_received": "10",
                "product_units_released": None,
            }
        ]
    )
    cleaned = _clean(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A",
                "product_units_received": 10.0,
                "product_units_released": None,
                "product_balance_status": "start",
            },
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Phantom Drug",
                "product_units_received": 5.0,
                "product_units_released": None,
                "product_balance_status": "start",
            },
        ]
    )
    coll = ErrorCollector()
    check_missing_groups(_explode_multi_product_cells(raw), cleaned, coll)
    assert any(
        "PHANTOM_GROUP" in e.error_message and "Phantom Drug" in e.error_message
        for e in coll.errors
    )


def test_row_count_delta_fires_when_counts_differ() -> None:
    raw = _raw(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A",
                "product_units_received": "10",
                "product_units_released": None,
            },
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A",
                "product_units_received": "20",
                "product_units_released": None,
            },
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A",
                "product_units_received": "30",
                "product_units_released": None,
            },
        ]
    )
    cleaned = _clean(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A",
                "product_units_received": 10.0,
                "product_units_released": None,
                "product_balance_status": "start",
            }
            # Cleaner dropped two rows
        ]
    )
    coll = ErrorCollector()
    check_row_count_delta(_explode_multi_product_cells(raw), cleaned, coll)
    assert any(
        "ROW_COUNT_DELTA" in e.error_message and "delta=-2" in e.error_message
        for e in coll.errors
    )


def test_row_count_delta_silent_when_counts_match() -> None:
    raw = _raw(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A",
                "product_units_received": "10",
                "product_units_released": None,
            }
        ]
    )
    cleaned = _clean(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "Insulin A",
                "product_units_received": 10.0,
                "product_units_released": None,
                "product_balance_status": "start",
            }
        ]
    )
    coll = ErrorCollector()
    check_row_count_delta(_explode_multi_product_cells(raw), cleaned, coll)
    assert len(coll) == 0


def test_column_null_rate_delta_fires_for_silent_loss() -> None:
    raw = _raw(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "A",
                "product_units_received": "10",
                "product_units_released": "5",
            },
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "B",
                "product_units_received": "20",
                "product_units_released": "5",
            },
        ]
    )
    cleaned = _clean(
        [
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "A",
                "product_units_received": 10.0,
                "product_units_released": None,  # cleaner dropped both
                "product_balance_status": "start",
            },
            {
                "file_name": "f",
                "product_sheet_name": "Jan24",
                "product": "B",
                "product_units_received": 20.0,
                "product_units_released": None,
                "product_balance_status": "end",
            },
        ]
    )
    coll = ErrorCollector()
    check_column_null_rate_delta(raw, cleaned, coll)
    assert any(
        "COLUMN_NULL_RATE_DELTA" in e.error_message and e.column == "product_units_released"
        for e in coll.errors
    )
