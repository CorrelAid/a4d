"""Tests for tracker metadata table generation."""

import hashlib
from pathlib import Path

import polars as pl
import pytest

from a4d.tables.metadata import create_table_tracker_metadata


@pytest.fixture
def fake_trackers(tmp_path: Path) -> Path:
    """Create a fake data_root with two clinic subfolders and three trackers."""
    data_root = tmp_path / "data"
    (data_root / "CLINIC_A").mkdir(parents=True)
    (data_root / "CLINIC_B").mkdir(parents=True)

    (data_root / "CLINIC_A" / "2024_A1_Tracker.xlsx").write_bytes(b"clinic A tracker 1 contents")
    (data_root / "CLINIC_A" / "2024_A2_Tracker.xlsx").write_bytes(b"clinic A tracker 2 contents")
    (data_root / "CLINIC_B" / "2024_B1_Tracker.xlsx").write_bytes(b"clinic B tracker contents")
    return data_root


@pytest.fixture
def fake_output_root(tmp_path: Path) -> Path:
    """Create an output_root where A1 is fully processed, A2 half-processed, B1 untouched."""
    output_root = tmp_path / "output"
    for subdir in (
        "patient_data_cleaned",
        "patient_data_raw",
        "product_data_cleaned",
        "product_data_raw",
    ):
        (output_root / subdir).mkdir(parents=True)

    # A1: full set of outputs across all four subdirs.
    for subdir, suffix in (
        ("patient_data_cleaned", "_patient_cleaned.parquet"),
        ("patient_data_raw", "_patient_raw.parquet"),
        ("product_data_cleaned", "_product_cleaned.parquet"),
        ("product_data_raw", "_product_raw.parquet"),
    ):
        (output_root / subdir / f"2024_A1_Tracker{suffix}").write_bytes(b"")

    # A2: only patient outputs (product arm skipped).
    (output_root / "patient_data_raw" / "2024_A2_Tracker_patient_raw.parquet").write_bytes(b"")
    (output_root / "patient_data_cleaned" / "2024_A2_Tracker_patient_cleaned.parquet").write_bytes(
        b""
    )

    # B1: no outputs.
    return output_root


def test_metadata_shape_and_schema(fake_trackers: Path, fake_output_root: Path):
    out_path = create_table_tracker_metadata(fake_trackers, fake_output_root)

    assert out_path == fake_output_root / "tables" / "tracker_metadata.parquet"
    assert out_path.exists()

    df = pl.read_parquet(out_path)
    assert df.shape == (3, 9)
    assert df.columns == [
        "file_name",
        "clinic_code",
        "md5",
        "patient_data_cleaned",
        "patient_data_raw",
        "product_data_cleaned",
        "product_data_raw",
        "complete",
        "timestamp",
    ]


def test_metadata_presence_flags(fake_trackers: Path, fake_output_root: Path):
    create_table_tracker_metadata(fake_trackers, fake_output_root)
    df = pl.read_parquet(fake_output_root / "tables" / "tracker_metadata.parquet").sort("file_name")

    rows = df.to_dicts()

    a1 = next(r for r in rows if r["file_name"] == "2024_A1_Tracker")
    assert a1["clinic_code"] == "CLINIC_A"
    assert a1["patient_data_raw"] is True
    assert a1["patient_data_cleaned"] is True
    assert a1["product_data_raw"] is True
    assert a1["product_data_cleaned"] is True
    assert a1["complete"] is True

    a2 = next(r for r in rows if r["file_name"] == "2024_A2_Tracker")
    assert a2["patient_data_raw"] is True
    assert a2["product_data_raw"] is False
    assert a2["complete"] is False

    b1 = next(r for r in rows if r["file_name"] == "2024_B1_Tracker")
    assert b1["clinic_code"] == "CLINIC_B"
    assert all(
        b1[s] is False
        for s in (
            "patient_data_raw",
            "patient_data_cleaned",
            "product_data_raw",
            "product_data_cleaned",
        )
    )
    assert b1["complete"] is False


def test_metadata_md5_matches_file_bytes(fake_trackers: Path, fake_output_root: Path):
    create_table_tracker_metadata(fake_trackers, fake_output_root)
    df = pl.read_parquet(fake_output_root / "tables" / "tracker_metadata.parquet")

    for row in df.iter_rows(named=True):
        tracker_path = fake_trackers / row["clinic_code"] / f"{row['file_name']}.xlsx"
        expected = hashlib.md5(tracker_path.read_bytes(), usedforsecurity=False).hexdigest()
        assert row["md5"] == expected


def test_metadata_handles_missing_output_subdirs(fake_trackers: Path, tmp_path: Path):
    """Empty output_root (no subdirs yet) should produce all-False presence flags."""
    output_root = tmp_path / "empty_output"
    output_root.mkdir()

    create_table_tracker_metadata(fake_trackers, output_root)
    df = pl.read_parquet(output_root / "tables" / "tracker_metadata.parquet")

    assert df.height == 3
    for col in (
        "patient_data_raw",
        "patient_data_cleaned",
        "product_data_raw",
        "product_data_cleaned",
    ):
        assert df[col].to_list() == [False, False, False]
    assert df["complete"].to_list() == [False, False, False]


def test_metadata_empty_data_root(tmp_path: Path):
    """Empty data_root should produce a zero-row parquet with correct schema."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    output_root = tmp_path / "output"
    output_root.mkdir()

    out_path = create_table_tracker_metadata(data_root, output_root)
    df = pl.read_parquet(out_path)

    assert df.height == 0
    assert df.columns == [
        "file_name",
        "clinic_code",
        "md5",
        "patient_data_cleaned",
        "patient_data_raw",
        "product_data_cleaned",
        "product_data_raw",
        "complete",
        "timestamp",
    ]
