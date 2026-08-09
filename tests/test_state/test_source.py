"""Tests for load_previous_manifest source-precedence logic."""

from pathlib import Path
from unittest.mock import patch

import polars as pl

from a4d.state.manifest import Manifest
from a4d.state.source import load_previous_manifest


def _manifest_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "file_name": ["2024_T1", "2024_T2"],
            "clinic_code": ["A", "B"],
            "md5": ["abc", "def"],
            "complete": [True, False],
        }
    )


def test_bigquery_first_when_available(tmp_path: Path):
    """BQ wins over local parquet when prefer_bigquery=True and BQ returns rows."""
    # Both sources populated; BQ should be picked.
    local = tmp_path / "tables" / "tracker_metadata.parquet"
    local.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "file_name": ["LOCAL_ONLY"],
            "clinic_code": ["X"],
            "md5": ["local_md5"],
            "complete": [True],
        }
    ).write_parquet(local)

    with patch("a4d.gcp.bigquery.select_tracker_metadata", return_value=_manifest_df()):
        m = load_previous_manifest(tmp_path)

    assert len(m) == 2
    assert m.get("A", "2024_T1").md5 == "abc"
    # Local parquet was NOT consulted.
    assert m.get("X", "LOCAL_ONLY") is None


def test_falls_back_to_local_parquet_when_bq_returns_none(tmp_path: Path):
    local = tmp_path / "tables" / "tracker_metadata.parquet"
    local.parent.mkdir(parents=True)
    _manifest_df().write_parquet(local)

    with patch("a4d.gcp.bigquery.select_tracker_metadata", return_value=None):
        m = load_previous_manifest(tmp_path)

    assert len(m) == 2
    assert m.get("A", "2024_T1").complete is True
    assert m.get("B", "2024_T2").complete is False


def test_returns_empty_when_neither_source_available(tmp_path: Path):
    with patch("a4d.gcp.bigquery.select_tracker_metadata", return_value=None):
        m = load_previous_manifest(tmp_path)

    assert m == Manifest.empty()


def test_skips_bigquery_when_prefer_bigquery_false(tmp_path: Path):
    local = tmp_path / "tables" / "tracker_metadata.parquet"
    local.parent.mkdir(parents=True)
    _manifest_df().write_parquet(local)

    # patch should never be called.
    with patch("a4d.gcp.bigquery.select_tracker_metadata") as mock_bq:
        m = load_previous_manifest(tmp_path, prefer_bigquery=False)
        assert mock_bq.call_count == 0

    assert len(m) == 2


def test_handles_corrupt_local_parquet(tmp_path: Path):
    local = tmp_path / "tables" / "tracker_metadata.parquet"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"not a parquet file")

    with patch("a4d.gcp.bigquery.select_tracker_metadata", return_value=None):
        m = load_previous_manifest(tmp_path)

    assert m == Manifest.empty()
