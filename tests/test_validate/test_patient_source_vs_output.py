"""Tests for source_vs_output_patient.

Fixtures pass ``schema={...}`` explicitly so all-None columns keep ``pl.Utf8``
dtype (per the polars all-None ``pl.Null`` inference trap).
"""

from __future__ import annotations

import polars as pl

from a4d.errors import ErrorCollector
from a4d.validate.common import normalize_patient_id
from a4d.validate.source_vs_output_patient import (
    _join_for_cell_checks,
    check_missing_patients,
    check_out_of_range,
    check_unexpected_nulls,
    check_value_shifts,
)

RAW_SCHEMA = {
    "clinic_id": pl.Utf8,
    "patient_id": pl.Utf8,
    "tracker_year": pl.Int64,
    "tracker_month": pl.Int64,
    "file_name": pl.Utf8,
    "weight": pl.Utf8,
    "height": pl.Utf8,
    "hba1c_updated": pl.Utf8,
}

CLEAN_SCHEMA = {
    "clinic_id": pl.Utf8,
    "patient_id": pl.Utf8,
    "tracker_year": pl.Int64,
    "tracker_month": pl.Int64,
    "file_name": pl.Utf8,
    "weight": pl.Float64,
    "height": pl.Float64,
    "hba1c_updated": pl.Float64,
}


def _make_raw(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=RAW_SCHEMA)


def _make_clean(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=CLEAN_SCHEMA)


def test_normalize_patient_id_strips_transfer_suffix() -> None:
    df = pl.DataFrame(
        {"patient_id": ["MY_QH003_SB", "LA-QA093_LF", "TH_QF001", "SOLO"]},
        schema={"patient_id": pl.Utf8},
    )
    out = df.with_columns(normalize_patient_id(pl.col("patient_id")).alias("n"))
    assert out["n"].to_list() == ["MY_QH003", "LA_QA093", "TH_QF001", "SOLO"]


def test_missing_patient_does_not_fire_for_transferred_id() -> None:
    raw = _make_raw(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003_SB",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": "70",
                "height": "1.7",
                "hba1c_updated": "7.0",
            }
        ]
    )
    cleaned = _make_clean(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",  # cleaner stripped suffix
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": 70.0,
                "height": 1.7,
                "hba1c_updated": 7.0,
            }
        ]
    )
    coll = ErrorCollector()
    check_missing_patients(raw, cleaned, coll)
    assert len(coll) == 0


def test_missing_patient_fires_when_truly_absent() -> None:
    raw = _make_raw(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": "70",
                "height": "1.7",
                "hba1c_updated": "7.0",
            },
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH999",  # absent in cleaned
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": "60",
                "height": "1.6",
                "hba1c_updated": "8.0",
            },
        ]
    )
    cleaned = _make_clean(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": 70.0,
                "height": 1.7,
                "hba1c_updated": 7.0,
            }
        ]
    )
    coll = ErrorCollector()
    check_missing_patients(raw, cleaned, coll)
    msgs = [e.error_message for e in coll.errors]
    assert any("MY_QH999" in m and "MISSING_ROW" in m for m in msgs)
    assert not any("PHANTOM_ROW" in m for m in msgs)


def test_value_shift_skips_height_unit_conversion() -> None:
    raw = _make_raw(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": "70",
                "height": "170",  # cm, cleaner divides by 100
                "hba1c_updated": "7.0",
            }
        ]
    )
    cleaned = _make_clean(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": 70.0,
                "height": 1.7,  # converted from 170 cm
                "hba1c_updated": 7.0,
            }
        ]
    )
    coll = ErrorCollector()
    joined = _join_for_cell_checks(raw, cleaned)
    check_value_shifts(joined, coll)
    # Should be zero shifts: weight matches, hba1c matches, height is skipped.
    shift_msgs = [e.error_message for e in coll.errors if "VALUE_SHIFT" in e.error_message]
    assert shift_msgs == []


def test_value_shift_fires_on_genuine_mismatch() -> None:
    raw = _make_raw(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": "70",
                "height": "1.7",
                "hba1c_updated": "7.0",
            }
        ]
    )
    cleaned = _make_clean(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": 99.0,  # mismatch
                "height": 1.7,
                "hba1c_updated": 7.0,
            }
        ]
    )
    coll = ErrorCollector()
    joined = _join_for_cell_checks(raw, cleaned)
    check_value_shifts(joined, coll)
    assert any("VALUE_SHIFT" in e.error_message and e.column == "weight" for e in coll.errors)


def test_unexpected_null_fires_when_raw_has_value_cleaned_does_not() -> None:
    raw = _make_raw(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": "70",
                "height": "1.7",
                "hba1c_updated": "7.0",
            }
        ]
    )
    cleaned = _make_clean(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": 70.0,
                "height": 1.7,
                "hba1c_updated": None,  # silently dropped despite parseable raw
            }
        ]
    )
    coll = ErrorCollector()
    joined = _join_for_cell_checks(raw, cleaned)
    check_unexpected_nulls(joined, coll)
    msgs = [e.error_message for e in coll.errors if e.column == "hba1c_updated"]
    assert msgs and "UNEXPECTED_NULL" in msgs[0] and "was_parseable=True" in msgs[0]


def test_out_of_range_height_skips_cm_value() -> None:
    """170 cm raw should NOT fire after the cm->m auto-conversion."""
    raw = _make_raw(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": "70",
                "height": "170",
                "hba1c_updated": "7.0",
            }
        ]
    )
    coll = ErrorCollector()
    check_out_of_range(raw, coll)
    height_findings = [e for e in coll.errors if e.column == "height"]
    assert height_findings == []


def test_out_of_range_height_fires_after_auto_conversion() -> None:
    """height=250 (cm) -> auto-converts to 2.5 m -> still exceeds max 2.3."""
    raw = _make_raw(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": "70",
                "height": "250",
                "hba1c_updated": "7.0",
            }
        ]
    )
    coll = ErrorCollector()
    check_out_of_range(raw, coll)
    assert any(
        e.column == "height" and "OUT_OF_RANGE_RAW" in e.error_message for e in coll.errors
    )


def test_out_of_range_weight_fires_for_obvious_outlier() -> None:
    raw = _make_raw(
        [
            {
                "clinic_id": "CDA",
                "patient_id": "MY_QH003",
                "tracker_year": 2024,
                "tracker_month": 1,
                "file_name": "f",
                "weight": "350",  # exceeds 200 max
                "height": "1.7",
                "hba1c_updated": "7.0",
            }
        ]
    )
    coll = ErrorCollector()
    check_out_of_range(raw, coll)
    assert any(e.column == "weight" for e in coll.errors)
