"""Tests for `a4d snapshot check` and `a4d snapshot update`."""

from __future__ import annotations

import polars as pl
import pytest
from typer.testing import CliRunner

from a4d.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})


@pytest.fixture
def run_output(tmp_path):
    """A data root holding one tracker and one stage of pipeline output."""
    data_root = tmp_path / "data"
    clinic = data_root / "TST"
    clinic.mkdir(parents=True)
    (clinic / "2024_Test Clinic A4D Tracker.xlsx").write_bytes(b"workbook-v1")

    cleaned = data_root / "output" / "patient_data_cleaned"
    cleaned.mkdir(parents=True)
    pl.DataFrame({"patient_id": ["A1", "A2"], "age": [10, 20]}).write_parquet(
        cleaned / "2024_Test Clinic A4D Tracker_patient_cleaned.parquet"
    )
    return data_root


def check(data_root, *extra):
    return runner.invoke(app, ["snapshot", "check", "--data-root", str(data_root), *extra])


def update(data_root, *extra):
    return runner.invoke(app, ["snapshot", "update", "--data-root", str(data_root), *extra])


class TestHelp:
    def test_check_help(self):
        result = runner.invoke(app, ["snapshot", "check", "--help"])
        assert result.exit_code == 0
        assert "--data-root" in result.output

    def test_update_help(self):
        result = runner.invoke(app, ["snapshot", "update", "--help"])
        assert result.exit_code == 0


class TestCheck:
    def test_first_check_has_no_baseline_and_says_so(self, run_output):
        result = check(run_output)
        assert result.exit_code == 1
        assert "no baseline" in result.output.lower()

    def test_first_check_still_writes_a_current_digest(self, run_output):
        check(run_output)
        assert (run_output / "snapshot" / "current.parquet").exists()

    def test_an_unchanged_run_passes(self, run_output):
        check(run_output)
        update(run_output)
        result = check(run_output)
        assert result.exit_code == 0
        assert "no movement" in result.output.lower()

    def test_changed_output_under_the_same_workbook_fails_as_a_regression(self, run_output):
        check(run_output)
        update(run_output)

        cleaned = run_output / "output" / "patient_data_cleaned"
        pl.DataFrame({"patient_id": ["A1", "A2"], "age": [10, 99]}).write_parquet(
            cleaned / "2024_Test Clinic A4D Tracker_patient_cleaned.parquet"
        )

        result = check(run_output)
        assert result.exit_code == 1
        assert "POSSIBLE REGRESSION" in result.output

    def test_an_edited_workbook_is_reported_as_expected_not_as_a_regression(self, run_output):
        check(run_output)
        update(run_output)

        (run_output / "TST" / "2024_Test Clinic A4D Tracker.xlsx").write_bytes(b"workbook-v2")
        cleaned = run_output / "output" / "patient_data_cleaned"
        pl.DataFrame({"patient_id": ["A1", "A2"], "age": [10, 99]}).write_parquet(
            cleaned / "2024_Test Clinic A4D Tracker_patient_cleaned.parquet"
        )

        result = check(run_output)
        assert result.exit_code == 1
        assert "workbook edited" in result.output
        assert "POSSIBLE REGRESSION" not in result.output

    def test_missing_output_is_an_error_not_an_empty_pass(self, run_output):
        """An empty digest would otherwise read as 'nothing moved'."""
        for parquet in (run_output / "output").rglob("*.parquet"):
            parquet.unlink()
        result = check(run_output)
        assert result.exit_code == 1
        assert "no pipeline output" in result.output.lower()


class TestUpdate:
    def test_update_promotes_the_last_check(self, run_output):
        check(run_output)
        result = update(run_output)
        assert result.exit_code == 0
        assert (run_output / "snapshot" / "baseline.parquet").exists()

    def test_update_without_a_check_refuses(self, run_output):
        result = update(run_output)
        assert result.exit_code == 1
        # Short phrase: the console wraps, so a longer one can straddle a newline.
        assert "No digest to promote" in result.output

    def test_update_runs_no_pipeline_and_reads_no_output(self, run_output):
        """Update only copies the digest forward -- it never recomputes."""
        check(run_output)
        for parquet in (run_output / "output").rglob("*.parquet"):
            parquet.unlink()

        result = update(run_output)
        assert result.exit_code == 0
        assert (run_output / "snapshot" / "baseline.parquet").exists()
