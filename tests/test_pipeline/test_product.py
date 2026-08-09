"""Tests for product pipeline orchestration (`pipeline/product.py`).

Previously untested at the orchestration level (only per-tracker extract/clean
functions had unit tests) -- process_tracker_product is monkeypatched here so
these tests don't need real Excel trackers.
"""

from datetime import date
from pathlib import Path

import polars as pl

from a4d.clean.schema_product import get_product_data_schema
from a4d.pipeline import product as product_pipeline
from a4d.pipeline.models import TrackerResult
from a4d.pipeline.product import process_product_tables, run_product_pipeline


def _write_cleaned_product_parquet(path: Path, released_to: str = "MY_SU001") -> Path:
    schema = get_product_data_schema()
    row = {
        "product": "Insulin A",
        "product_units_notes": None,
        "product_entry_date": date(2024, 1, 15),
        "product_units_released": 5.0,
        "product_released_to": released_to,
        "product_units_received": None,
        "product_received_from": "HQ",
        "product_balance": 10.0,
        "product_units_returned": None,
        "product_returned_by": None,
        "product_table_month": 1,
        "product_table_year": 2024,
        "product_sheet_name": "Jan24",
        "file_name": path.name,
        "product_balance_status": "ok",
        "product_category": "Insulin",
        "orig_product_released_to": None,
        "product_unit_capacity": 1,
        "product_remarks": None,
        "clinic_id": "SU",
    }
    pl.DataFrame([row], schema=schema).write_parquet(path)
    return path


class TestProcessProductTables:
    def test_no_cleaned_files_returns_empty(self, tmp_path: Path):
        cleaned_dir = tmp_path / "product_data_cleaned"
        cleaned_dir.mkdir()
        output_dir = tmp_path / "tables"

        result = process_product_tables(cleaned_dir, output_dir)

        assert result == {}

    def test_creates_product_data_table(self, tmp_path: Path):
        cleaned_dir = tmp_path / "product_data_cleaned"
        cleaned_dir.mkdir()
        _write_cleaned_product_parquet(cleaned_dir / "tracker_a_product_cleaned.parquet")
        output_dir = tmp_path / "tables"

        result = process_product_tables(cleaned_dir, output_dir)

        assert "product_data" in result
        assert result["product_data"].exists()


class TestRunProductPipeline:
    def test_no_tracker_files_returns_empty_result(self, tmp_path: Path):
        result = run_product_pipeline(tracker_files=[], output_root=tmp_path)

        assert result.total_trackers == 0
        assert result.success is True

    def test_sequential_processes_trackers_successfully(self, tmp_path: Path, monkeypatch):
        tracker_file = tmp_path / "tracker_a.xlsx"
        tracker_file.write_bytes(b"fake")

        def fake_process(tracker_file, output_root, mapper=None):
            return TrackerResult(
                tracker_file=tracker_file,
                tracker_name=tracker_file.stem,
                raw_output=None,
                cleaned_output=None,
                success=True,
                cleaning_errors=0,
            )

        monkeypatch.setattr(product_pipeline, "process_tracker_product", fake_process)

        result = run_product_pipeline(
            tracker_files=[tracker_file],
            output_root=tmp_path,
            skip_tables=True,
            max_workers=1,
        )

        assert result.total_trackers == 1
        assert result.successful_trackers == 1
        assert result.failed_trackers == 0
        assert result.success is True

    def test_sequential_records_failed_tracker(self, tmp_path: Path, monkeypatch):
        tracker_file = tmp_path / "tracker_bad.xlsx"
        tracker_file.write_bytes(b"fake")

        def fake_process(tracker_file, output_root, mapper=None):
            return TrackerResult(
                tracker_file=tracker_file,
                tracker_name=tracker_file.stem,
                success=False,
                error="boom",
            )

        monkeypatch.setattr(product_pipeline, "process_tracker_product", fake_process)

        result = run_product_pipeline(
            tracker_files=[tracker_file],
            output_root=tmp_path,
            skip_tables=True,
            max_workers=1,
        )

        assert result.failed_trackers == 1
        assert result.success is False

    def test_creates_tables_when_not_skipped(self, tmp_path: Path, monkeypatch):
        tracker_file = tmp_path / "tracker_a.xlsx"
        tracker_file.write_bytes(b"fake")

        def fake_process(tracker_file, output_root, mapper=None):
            cleaned_dir = output_root / "product_data_cleaned"
            cleaned_dir.mkdir(parents=True, exist_ok=True)
            cleaned_output = cleaned_dir / f"{tracker_file.stem}_product_cleaned.parquet"
            _write_cleaned_product_parquet(cleaned_output)
            return TrackerResult(
                tracker_file=tracker_file,
                tracker_name=tracker_file.stem,
                cleaned_output=cleaned_output,
                success=True,
            )

        monkeypatch.setattr(product_pipeline, "process_tracker_product", fake_process)

        result = run_product_pipeline(
            tracker_files=[tracker_file],
            output_root=tmp_path,
            skip_tables=False,
            max_workers=1,
        )

        assert "product_data" in result.tables
        assert result.tables["product_data"].exists()

    def test_clean_output_removes_existing_output_dirs(self, tmp_path: Path, monkeypatch):
        raw_dir = tmp_path / "product_data_raw"
        cleaned_dir = tmp_path / "product_data_cleaned"
        raw_dir.mkdir()
        cleaned_dir.mkdir()
        (raw_dir / "stale_raw.parquet").write_bytes(b"stale")
        (cleaned_dir / "stale_cleaned.parquet").write_bytes(b"stale")

        tables_dir = tmp_path / "tables"
        tables_dir.mkdir()
        stale_table = tables_dir / "product_data.parquet"
        stale_table.write_bytes(b"stale")

        monkeypatch.setattr(
            product_pipeline,
            "process_tracker_product",
            lambda tracker_file, output_root, mapper=None: TrackerResult(
                tracker_file=tracker_file, tracker_name=tracker_file.stem, success=True
            ),
        )

        run_product_pipeline(
            tracker_files=[],
            output_root=tmp_path,
            clean_output=True,
            skip_tables=True,
        )

        assert not raw_dir.exists()
        assert not cleaned_dir.exists()
        assert not stale_table.exists()
