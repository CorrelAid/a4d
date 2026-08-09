"""Producer/consumer round-trip for the incremental-processing manifest.

Avoids invoking the patient/product orchestrators (which need real .xlsx
structure) — instead exercises the metadata builder → manifest loader → filter
pipeline against synthetic byte-blobs that look like trackers on disk.
"""

from pathlib import Path

import pytest

from a4d.state.filter import filter_unchanged_trackers
from a4d.state.source import load_previous_manifest
from a4d.tables.metadata import create_table_tracker_metadata


@pytest.fixture
def fake_pipeline_run(tmp_path: Path):
    """Create a 2-tracker fake data_root + fully-populated output subdirs."""
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"

    (data_root / "CLINIC_A").mkdir(parents=True)
    t1 = data_root / "CLINIC_A" / "2024_T1_Tracker.xlsx"
    t1.write_bytes(b"tracker one bytes")
    t2 = data_root / "CLINIC_A" / "2024_T2_Tracker.xlsx"
    t2.write_bytes(b"tracker two bytes")

    # Simulate a successful run: every tracker has all four output stages.
    for subdir in (
        "patient_data_cleaned",
        "patient_data_raw",
        "product_data_cleaned",
        "product_data_raw",
    ):
        (output_root / subdir).mkdir(parents=True)
        for stem in ("2024_T1_Tracker", "2024_T2_Tracker"):
            (output_root / subdir / f"{stem}_dummy.parquet").write_bytes(b"")

    # Publish the manifest — same call the `run` CLI command makes at end of run.
    create_table_tracker_metadata(data_root, output_root)

    return {"data_root": data_root, "output_root": output_root, "t1": t1, "t2": t2}


def test_published_manifest_skips_all_unchanged(fake_pipeline_run):
    """Round-trip 1: metadata published as complete=True ⇒ next run queues 0."""
    data_root = fake_pipeline_run["data_root"]
    output_root = fake_pipeline_run["output_root"]

    discovered = sorted(data_root.rglob("*.xlsx"))
    manifest = load_previous_manifest(output_root, prefer_bigquery=False)

    queued, summary = filter_unchanged_trackers(discovered, manifest)

    assert queued == []
    assert summary.skipped == 2
    assert summary.queued == 0


def test_mutated_tracker_queues_exactly_one(fake_pipeline_run):
    """Round-trip 2: change one tracker's bytes ⇒ filter queues exactly it."""
    data_root = fake_pipeline_run["data_root"]
    output_root = fake_pipeline_run["output_root"]
    t1 = fake_pipeline_run["t1"]

    # Mutate t1's bytes — t2 stays untouched.
    t1.write_bytes(b"tracker one with new bytes")

    discovered = sorted(data_root.rglob("*.xlsx"))
    manifest = load_previous_manifest(output_root, prefer_bigquery=False)
    queued, summary = filter_unchanged_trackers(discovered, manifest)

    assert queued == [t1]
    assert summary.changed == 1
    assert summary.skipped == 1


def test_missing_output_stage_marks_incomplete_and_requeues(tmp_path: Path):
    """If product_data_cleaned/ is missing for a tracker, complete=False ⇒ requeue."""
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"

    (data_root / "CLINIC_A").mkdir(parents=True)
    t1 = data_root / "CLINIC_A" / "2024_T1_Tracker.xlsx"
    t1.write_bytes(b"alpha")

    # Only three of four stages have output — simulates a previous run that
    # crashed during the product arm.
    for subdir in ("patient_data_cleaned", "patient_data_raw", "product_data_raw"):
        (output_root / subdir).mkdir(parents=True)
        (output_root / subdir / "2024_T1_Tracker_dummy.parquet").write_bytes(b"")

    create_table_tracker_metadata(data_root, output_root)

    manifest = load_previous_manifest(output_root, prefer_bigquery=False)
    queued, summary = filter_unchanged_trackers([t1], manifest)

    assert queued == [t1]
    assert summary.previously_incomplete == 1
    assert summary.changed == 0
