"""Tests for `link_product_patient` — product↔patient link validation."""

from collections.abc import Iterator
from pathlib import Path

import polars as pl
import pytest
from loguru import logger

from a4d.tables.product import link_product_patient


@pytest.fixture
def captured_warnings() -> Iterator[list[str]]:
    """Capture loguru WARNING messages emitted during the test."""
    sink: list[str] = []
    handler_id = logger.add(
        lambda msg: sink.append(str(msg)),
        level="WARNING",
        format="{message}",
    )
    yield sink
    logger.remove(handler_id)


def _write_patient_static(path: Path, rows: list[tuple[str, str]]) -> Path:
    """Write a minimal patient_data_static.parquet with (file_name, patient_id) rows."""
    pl.DataFrame(
        {"file_name": [r[0] for r in rows], "patient_id": [r[1] for r in rows]}
    ).write_parquet(path)
    return path


def test_all_match_returns_zero_no_warnings(tmp_path: Path, captured_warnings: list[str]) -> None:
    patient_path = _write_patient_static(
        tmp_path / "patient.parquet",
        [
            ("tracker_a.xlsx", "KD_QB001"),
            ("tracker_a.xlsx", "KD_QB002"),
            ("tracker_b.xlsx", "KD_QB003"),
        ],
    )
    product_df = pl.DataFrame(
        {
            "file_name": [
                "tracker_a.xlsx",
                "tracker_a.xlsx",
                "tracker_a.xlsx",
                "tracker_b.xlsx",
                "tracker_b.xlsx",
            ],
            "product_released_to": [
                "KD_QB001",
                "KD_QB001",
                "KD_QB002",
                "KD_QB003",
                "KD_QB003",
            ],
        }
    )

    count = link_product_patient(product_df, patient_path)

    assert count == 0
    assert captured_warnings == []


def test_mixed_filters_null_and_sentinel(tmp_path: Path, captured_warnings: list[str]) -> None:
    patient_path = _write_patient_static(
        tmp_path / "patient.parquet",
        [("tracker_a.xlsx", "KD_QB001"), ("tracker_a.xlsx", "KD_QB002")],
    )
    product_df = pl.DataFrame(
        {
            "file_name": [
                "tracker_a.xlsx",  # match
                "tracker_a.xlsx",  # match
                "tracker_a.xlsx",  # match
                "tracker_a.xlsx",  # mismatch
                "tracker_a.xlsx",  # mismatch
                "tracker_a.xlsx",  # null — filtered
                "tracker_a.xlsx",  # "Undefined" — filtered
            ],
            "product_released_to": [
                "KD_QB001",
                "KD_QB001",
                "KD_QB002",
                "KD_QB999",
                "KD_QB999",
                None,
                "Undefined",
            ],
        }
    )

    count = link_product_patient(product_df, patient_path)

    assert count == 2
    # One warning per distinct (file, id) mismatch pair → 1 group → 1 warning
    mismatch_warnings = [w for w in captured_warnings if "Unmatched product_released_to" in w]
    assert len(mismatch_warnings) == 1
    assert "tracker_a.xlsx" in mismatch_warnings[0]
    assert "KD_QB999" in mismatch_warnings[0]
    assert "count=2" in mismatch_warnings[0]


def test_cross_file_isolation(tmp_path: Path, captured_warnings: list[str]) -> None:
    """Same patient_id matches in one file but not in another."""
    patient_path = _write_patient_static(
        tmp_path / "patient.parquet",
        [("tracker_a.xlsx", "KD_QB001")],
    )
    product_df = pl.DataFrame(
        {
            "file_name": ["tracker_a.xlsx", "tracker_b.xlsx"],
            "product_released_to": ["KD_QB001", "KD_QB001"],
        }
    )

    count = link_product_patient(product_df, patient_path)

    assert count == 1
    mismatch_warnings = [w for w in captured_warnings if "Unmatched product_released_to" in w]
    assert len(mismatch_warnings) == 1
    assert "tracker_b.xlsx" in mismatch_warnings[0]
    assert "KD_QB001" in mismatch_warnings[0]


def test_missing_patient_table_returns_zero_with_warning(
    tmp_path: Path, captured_warnings: list[str]
) -> None:
    product_df = pl.DataFrame(
        {"file_name": ["tracker_a.xlsx"], "product_released_to": ["KD_QB001"]}
    )
    missing_path = tmp_path / "does_not_exist.parquet"

    count = link_product_patient(product_df, missing_path)

    assert count == 0
    skip_warnings = [w for w in captured_warnings if "skipping" in w.lower()]
    assert len(skip_warnings) == 1
