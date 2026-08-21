"""Tests for the A4D CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
from typer.testing import CliRunner

from a4d.cli import app
from a4d.errors import DataError
from a4d.pipeline.models import PipelineResult, TrackerResult

runner = CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})


# ---------------------------------------------------------------------------
# Help / invocation smoke tests
# ---------------------------------------------------------------------------


class TestHelp:
    """Verify every command exposes --help without error."""

    def test_app_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output

    def test_run_patient_help(self):
        result = runner.invoke(app, ["run", "patient", "--help"])
        assert result.exit_code == 0
        assert "--file" in result.output

    def test_create_tables_help(self):
        result = runner.invoke(app, ["create", "tables", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.output

    def test_upload_tables_help(self):
        result = runner.invoke(app, ["upload", "tables", "--help"])
        assert result.exit_code == 0
        assert "--tables-dir" in result.output

    def test_run_pipeline_help(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--skip-download" in result.output
        assert "--skip-upload" in result.output
        assert "--skip-patient" in result.output


# ---------------------------------------------------------------------------
# Error-path unit tests (no real files needed)
# ---------------------------------------------------------------------------


class TestCreateTablesErrors:
    """create tables command error handling."""

    def test_no_cleaned_dirs_exits_nonzero(self, tmp_path):
        # Output root exists but has neither patient_data_cleaned/ nor
        # product_data_cleaned/ — nothing to build tables from.
        result = runner.invoke(app, ["create", "tables", "--output", str(tmp_path)])
        assert result.exit_code == 1
        assert "nothing to build tables from" in result.output

    def test_missing_output_dir_exits_nonzero(self, tmp_path):
        missing = tmp_path / "nonexistent"
        result = runner.invoke(app, ["create", "tables", "--output", str(missing)])
        assert result.exit_code == 1


class TestUploadTablesErrors:
    """upload tables command error handling."""

    def test_missing_dir_exits_nonzero(self, tmp_path):
        missing = tmp_path / "nonexistent_tables"
        result = runner.invoke(app, ["upload", "tables", "--tables-dir", str(missing)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# `run` unit test (GCS/BQ mocked)
# ---------------------------------------------------------------------------


class TestRunPipeline:
    """`run` command with mocked GCP calls."""

    @patch("a4d.cli.run_product_pipeline")
    @patch("a4d.cli.run_patient_pipeline")
    @patch("a4d.config.settings")
    def test_errors_table_holds_both_arms(
        self, mock_settings, mock_run_patient, mock_run_product, tmp_path
    ):
        """`run` is the production entry point, and until ticket 32 it published
        an errors table holding the patient arm only: the patient arm writes the
        table from inside its own pipeline, and nothing wrote the product arm's
        at all. The source-defect report (ticket 40) derives from this table, so
        a silently patient-only table loses every product finding."""
        mock_settings.data_root = tmp_path / "data"
        mock_settings.output_root = tmp_path / "output"
        mock_settings.project_id = "test-project"
        mock_settings.dataset = "test-dataset"
        mock_settings.max_workers = 4
        (tmp_path / "data").mkdir()
        (tmp_path / "output").mkdir()

        def _result(arm: str) -> PipelineResult:
            error = DataError(
                file_name=f"{arm}.xlsx",
                patient_id="P1",
                column="c",
                original_value="v",
                error_message=f"{arm} problem",
                error_code="invalid_value",
                script="clean",
                function_name="f",
            )
            return PipelineResult(
                tracker_results=[
                    TrackerResult(
                        tracker_file=Path(f"{arm}.xlsx"),
                        tracker_name=arm,
                        success=True,
                        cleaning_errors=1,
                        data_errors=[error],
                    )
                ],
                tables={},
                total_trackers=1,
                successful_trackers=1,
                failed_trackers=0,
                success=True,
            )

        mock_run_patient.return_value = _result("patient")
        mock_run_product.return_value = _result("product")

        result = runner.invoke(
            app, ["run", "--skip-download", "--skip-upload", "--skip-drive-download"]
        )

        assert result.exit_code == 0
        errors = pl.read_parquet(tmp_path / "output" / "tables" / "table_errors.parquet")
        assert set(errors["file_name"].to_list()) == {"patient.xlsx", "product.xlsx"}

    @patch("a4d.cli.run_product_pipeline")
    @patch("a4d.cli.run_patient_pipeline")
    @patch("a4d.config.settings")
    def test_skip_upload_calls_pipeline(
        self, mock_settings, mock_run_patient, mock_run_product, tmp_path
    ):
        # Both arms must be mocked, not just patient: `run_product_pipeline`
        # binds `settings` at its own module-import time, so patching
        # `a4d.config.settings` alone does not stop it discovering trackers
        # from the *real* local data_root if left unmocked.
        mock_settings.data_root = tmp_path / "data"
        mock_settings.output_root = tmp_path / "output"
        mock_settings.project_id = "test-project"
        mock_settings.dataset = "test-dataset"
        mock_settings.max_workers = 4

        (tmp_path / "data").mkdir()
        (tmp_path / "output").mkdir()

        empty_result = PipelineResult(
            tracker_results=[],
            tables={},
            total_trackers=0,
            successful_trackers=0,
            failed_trackers=0,
            success=True,
        )
        mock_run_patient.return_value = empty_result
        mock_run_product.return_value = empty_result

        result = runner.invoke(
            app, ["run", "--skip-download", "--skip-upload", "--skip-drive-download"]
        )

        mock_run_patient.assert_called_once()
        mock_run_product.assert_called_once()
        assert result.exit_code == 0

    @patch("a4d.cli.run_product_pipeline")
    @patch("a4d.cli.run_patient_pipeline")
    @patch("a4d.config.settings")
    def test_patient_failure_soft_fails_and_continues(
        self, mock_settings, mock_run_patient, mock_run_product, tmp_path
    ):
        """A patient tracker failure warns and continues rather than aborting
        the run (product/tables/upload still execute) — matches the product
        arm's existing soft-fail posture."""
        mock_settings.data_root = tmp_path / "data"
        mock_settings.output_root = tmp_path / "output"
        mock_settings.project_id = "test-project"
        mock_settings.dataset = "test-dataset"
        mock_settings.max_workers = 4

        (tmp_path / "data").mkdir()
        (tmp_path / "output").mkdir()

        mock_run_patient.return_value = PipelineResult(
            tracker_results=[_tracker_result("bad", success=False, error="Parse error")],
            tables={},
            total_trackers=1,
            successful_trackers=0,
            failed_trackers=1,
            success=False,
        )
        mock_run_product.return_value = PipelineResult(
            tracker_results=[],
            tables={},
            total_trackers=0,
            successful_trackers=0,
            failed_trackers=0,
            success=True,
        )

        result = runner.invoke(
            app, ["run", "--skip-download", "--skip-upload", "--skip-drive-download"]
        )

        assert result.exit_code == 0, result.output
        assert "some patient trackers failed" in result.output.lower()

    @patch("a4d.cli.run_product_pipeline")
    @patch("a4d.cli.run_patient_pipeline")
    @patch("a4d.config.settings")
    def test_skip_patient_runs_product_only(
        self, mock_settings, mock_run_patient, mock_run_product, tmp_path
    ):
        mock_settings.data_root = tmp_path / "data"
        mock_settings.output_root = tmp_path / "output"
        mock_settings.project_id = "test-project"
        mock_settings.dataset = "test-dataset"
        mock_settings.max_workers = 4

        (tmp_path / "data").mkdir()
        (tmp_path / "output").mkdir()

        mock_product = MagicMock()
        mock_product.success = True
        mock_product.total_trackers = 0
        mock_product.successful_trackers = 0
        mock_product.failed_trackers = 0
        mock_product.tracker_results = []
        mock_run_product.return_value = mock_product

        result = runner.invoke(
            app,
            [
                "run",
                "--skip-patient",
                "--skip-download",
                "--skip-upload",
                "--skip-drive-download",
            ],
        )

        assert result.exit_code == 0, f"Pipeline failed:\n{result.output}"
        mock_run_patient.assert_not_called()
        mock_run_product.assert_called_once()

    def test_skip_patient_and_skip_product_mutually_exclusive(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "run",
                "--skip-patient",
                "--skip-product",
                "--skip-download",
                "--skip-upload",
                "--skip-drive-download",
            ],
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output.lower()


# ---------------------------------------------------------------------------
# Combined patient+product run summary (ticket 11)
# ---------------------------------------------------------------------------


def _tracker_result(name, *, success=True, error=None, cleaning_errors=0):
    return TrackerResult(
        tracker_file=Path(f"{name}.xlsx"),
        tracker_name=name,
        success=success,
        error=error,
        cleaning_errors=cleaning_errors,
    )


class TestCombinedRunSummary:
    """`run`'s combined patient+product summary, only shown when both arms ran."""

    def _run(
        self, mock_settings, mock_run_patient, mock_run_product, tmp_path, patient_trs, product_trs
    ):
        mock_settings.data_root = tmp_path / "data"
        mock_settings.output_root = tmp_path / "output"
        mock_settings.project_id = "test-project"
        mock_settings.dataset = "test-dataset"
        mock_settings.max_workers = 4
        (tmp_path / "data").mkdir()
        (tmp_path / "output").mkdir()

        patient_result = PipelineResult(
            tracker_results=patient_trs,
            tables={},
            total_trackers=len(patient_trs),
            successful_trackers=sum(tr.success for tr in patient_trs),
            failed_trackers=sum(not tr.success for tr in patient_trs),
            success=all(tr.success for tr in patient_trs),
        )
        product_result = PipelineResult(
            tracker_results=product_trs,
            tables={},
            total_trackers=len(product_trs),
            successful_trackers=sum(tr.success for tr in product_trs),
            failed_trackers=sum(not tr.success for tr in product_trs),
            success=all(tr.success for tr in product_trs),
        )
        mock_run_patient.return_value = patient_result
        mock_run_product.return_value = product_result

        return runner.invoke(
            app,
            ["run", "--skip-download", "--skip-upload", "--skip-drive-download"],
        )

    @patch("a4d.cli.run_product_pipeline")
    @patch("a4d.cli.run_patient_pipeline")
    @patch("a4d.config.settings")
    def test_both_arms_ok(self, mock_settings, mock_run_patient, mock_run_product, tmp_path):
        patient_trs = [_tracker_result("2024_Clinic_A")]
        product_trs = [_tracker_result("2024_Clinic_A")]
        result = self._run(
            mock_settings, mock_run_patient, mock_run_product, tmp_path, patient_trs, product_trs
        )

        assert result.exit_code == 0, result.output
        assert "Combined Run Summary" in result.output
        assert "Files needing attention" not in result.output

    @patch("a4d.cli.run_product_pipeline")
    @patch("a4d.cli.run_patient_pipeline")
    @patch("a4d.config.settings")
    def test_patient_failed_only(self, mock_settings, mock_run_patient, mock_run_product, tmp_path):
        patient_trs = [_tracker_result("2024_Clinic_B", success=False, error="bad header")]
        product_trs = [_tracker_result("2024_Clinic_B")]
        result = self._run(
            mock_settings, mock_run_patient, mock_run_product, tmp_path, patient_trs, product_trs
        )

        assert result.exit_code == 0, result.output
        assert "Files needing attention" in result.output
        assert "2024_Clinic_B" in result.output
        assert "bad header" in result.output

    @patch("a4d.cli.run_product_pipeline")
    @patch("a4d.cli.run_patient_pipeline")
    @patch("a4d.config.settings")
    def test_file_lost_in_both_arms(
        self, mock_settings, mock_run_patient, mock_run_product, tmp_path
    ):
        patient_trs = [_tracker_result("2024_Clinic_C", success=False, error="patient boom")]
        product_trs = [_tracker_result("2024_Clinic_C", success=False, error="product boom")]
        result = self._run(
            mock_settings, mock_run_patient, mock_run_product, tmp_path, patient_trs, product_trs
        )

        assert result.exit_code == 0, result.output
        assert "patient boom" in result.output
        assert "product boom" in result.output

    @patch("a4d.cli.run_product_pipeline")
    @patch("a4d.config.settings")
    def test_omitted_when_product_arm_skipped(self, mock_settings, mock_run_product, tmp_path):
        mock_settings.data_root = tmp_path / "data"
        mock_settings.output_root = tmp_path / "output"
        mock_settings.project_id = "test-project"
        mock_settings.dataset = "test-dataset"
        mock_settings.max_workers = 4
        (tmp_path / "data").mkdir()
        (tmp_path / "output").mkdir()

        mock_run_product.return_value = PipelineResult(
            tracker_results=[],
            tables={},
            total_trackers=0,
            successful_trackers=0,
            failed_trackers=0,
            success=True,
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--skip-patient",
                "--skip-download",
                "--skip-upload",
                "--skip-drive-download",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Combined Run Summary" not in result.output


# ---------------------------------------------------------------------------
# End-to-end test: run patient with real dummy tracker
# ---------------------------------------------------------------------------


class TestProcessPatientE2E:
    """End-to-end test for run patient using a synthetic tracker file."""

    def test_process_single_file_creates_outputs(self, dummy_tracker, tmp_path):
        """run patient --file <dummy> --output <tmp> should produce parquet outputs."""
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "run",
                "patient",
                "--file",
                str(dummy_tracker),
                "--output",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0, f"Pipeline failed:\n{result.output}"

        # Raw parquet should be created
        raw_dir = output_dir / "patient_data_raw"
        raw_files = list(raw_dir.glob("*_patient_raw.parquet"))
        assert len(raw_files) == 1, f"Expected 1 raw parquet, found {len(raw_files)}"

        # Cleaned parquet should be created
        cleaned_dir = output_dir / "patient_data_cleaned"
        cleaned_files = list(cleaned_dir.glob("*_patient_cleaned.parquet"))
        assert len(cleaned_files) == 1, f"Expected 1 cleaned parquet, found {len(cleaned_files)}"

        # Validate cleaned parquet has expected columns and rows
        df_cleaned = pl.read_parquet(cleaned_files[0])
        assert "patient_id" in df_cleaned.columns
        assert "clinic_id" in df_cleaned.columns
        assert "tracker_year" in df_cleaned.columns
        assert len(df_cleaned) == 2  # 2 patients in dummy file

        # clinic_id is derived from parent folder name
        assert df_cleaned["clinic_id"].unique().to_list() == ["TST"]
        assert df_cleaned["tracker_year"].unique().to_list() == [2024]

    def test_process_single_file_creates_tables(self, dummy_tracker, tmp_path):
        """Tables (static, monthly, annual) should be created by default."""
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "run",
                "patient",
                "--file",
                str(dummy_tracker),
                "--output",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0, f"Pipeline failed:\n{result.output}"

        tables_dir = output_dir / "tables"
        assert (tables_dir / "patient_data_monthly.parquet").exists()
        assert (tables_dir / "patient_data_static.parquet").exists()

    def test_skip_tables_flag(self, dummy_tracker, tmp_path):
        """--skip-tables should skip table creation."""
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "run",
                "patient",
                "--file",
                str(dummy_tracker),
                "--output",
                str(output_dir),
                "--skip-tables",
            ],
        )

        assert result.exit_code == 0, f"Pipeline failed:\n{result.output}"

        tables_dir = output_dir / "tables"
        # Patient tables are skipped, but errors table is always written
        skipped_names = [
            "patient_data_static.parquet",
            "patient_data_monthly.parquet",
            "patient_data_annual.parquet",
        ]
        for name in skipped_names:
            assert not (tables_dir / name).exists(), f"{name} should not exist with --skip-tables"
        assert (tables_dir / "table_errors.parquet").exists(), (
            "errors table should always be written"
        )

    def test_process_missing_file_exits_nonzero(self, tmp_path):
        """Passing a non-existent file should exit with error."""
        missing = tmp_path / "ghost.xlsx"
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            ["run", "patient", "--file", str(missing), "--output", str(output_dir)],
        )

        assert result.exit_code == 1


class TestProcessProductE2E:
    """End-to-end test for run product, mirroring TestProcessPatientE2E.

    Covers the logs/errors table steps added to process_product_cmd to
    bring it to parity with process_patient_cmd (previously product never
    created a logs or errors table at all).
    """

    def test_process_single_file_creates_outputs(self, dummy_product_tracker, tmp_path):
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "run",
                "product",
                "--file",
                str(dummy_product_tracker),
                "--output",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0, f"Pipeline failed:\n{result.output}"

        raw_dir = output_dir / "product_data_raw"
        assert len(list(raw_dir.glob("*_product_raw.parquet"))) == 1

        cleaned_dir = output_dir / "product_data_cleaned"
        cleaned_files = list(cleaned_dir.glob("*_product_cleaned.parquet"))
        assert len(cleaned_files) == 1

        df_cleaned = pl.read_parquet(cleaned_files[0])
        assert "product" in df_cleaned.columns
        assert "clinic_id" in df_cleaned.columns
        assert df_cleaned["clinic_id"].unique().to_list() == ["TST"]

    def test_process_single_file_creates_tables(self, dummy_product_tracker, tmp_path):
        """Product table, logs table, and errors table should all be created by default."""
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "run",
                "product",
                "--file",
                str(dummy_product_tracker),
                "--output",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0, f"Pipeline failed:\n{result.output}"

        tables_dir = output_dir / "tables"
        assert (tables_dir / "product_data.parquet").exists()
        assert (tables_dir / "table_logs.parquet").exists(), (
            "logs table should be created (parity with run patient)"
        )
        assert (tables_dir / "table_errors.parquet").exists(), (
            "errors table should be created (parity with run patient)"
        )

    def test_skip_tables_flag(self, dummy_product_tracker, tmp_path):
        """--skip-tables should skip the product table, but errors table is always written."""
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "run",
                "product",
                "--file",
                str(dummy_product_tracker),
                "--output",
                str(output_dir),
                "--skip-tables",
            ],
        )

        assert result.exit_code == 0, f"Pipeline failed:\n{result.output}"

        tables_dir = output_dir / "tables"
        assert not (tables_dir / "product_data.parquet").exists()
        assert not (tables_dir / "table_logs.parquet").exists()
        assert (tables_dir / "table_errors.parquet").exists(), (
            "errors table should always be written"
        )

    def test_process_missing_file_exits_nonzero(self, tmp_path):
        missing = tmp_path / "ghost.xlsx"
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            ["run", "product", "--file", str(missing), "--output", str(output_dir)],
        )

        assert result.exit_code == 1
