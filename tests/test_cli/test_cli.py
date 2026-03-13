"""Tests for the A4D CLI commands."""

from unittest.mock import MagicMock, patch

import polars as pl
from typer.testing import CliRunner

from a4d.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})


# ---------------------------------------------------------------------------
# Help / invocation smoke tests
# ---------------------------------------------------------------------------


class TestHelp:
    """Verify every command exposes --help without error."""

    def test_app_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "process-patient" in result.output

    def test_process_patient_help(self):
        result = runner.invoke(app, ["process-patient", "--help"])
        assert result.exit_code == 0
        assert "--file" in result.output

    def test_create_tables_help(self):
        result = runner.invoke(app, ["create-tables", "--help"])
        assert result.exit_code == 0
        assert "--input" in result.output

    def test_upload_tables_help(self):
        result = runner.invoke(app, ["upload-tables", "--help"])
        assert result.exit_code == 0
        assert "--tables-dir" in result.output

    def test_run_pipeline_help(self):
        result = runner.invoke(app, ["run-pipeline", "--help"])
        assert result.exit_code == 0
        assert "--skip-download" in result.output
        assert "--skip-upload" in result.output


# ---------------------------------------------------------------------------
# Error-path unit tests (no real files needed)
# ---------------------------------------------------------------------------


class TestCreateTablesErrors:
    """create-tables command error handling."""

    def test_no_parquet_files_exits_nonzero(self, tmp_path):
        # Directory exists but contains no *_patient_cleaned.parquet files
        result = runner.invoke(app, ["create-tables", "--input", str(tmp_path)])
        assert result.exit_code == 1
        assert "No cleaned parquet files found" in result.output

    def test_missing_input_dir_raises(self, tmp_path):
        missing = tmp_path / "nonexistent"
        result = runner.invoke(app, ["create-tables", "--input", str(missing)])
        # typer raises UsageError or the command fails when dir missing
        assert result.exit_code != 0


class TestUploadTablesErrors:
    """upload-tables command error handling."""

    def test_missing_dir_exits_nonzero(self, tmp_path):
        missing = tmp_path / "nonexistent_tables"
        result = runner.invoke(app, ["upload-tables", "--tables-dir", str(missing)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# run-pipeline unit test (GCS/BQ mocked)
# ---------------------------------------------------------------------------


class TestRunPipeline:
    """run-pipeline command with mocked GCP calls."""

    @patch("a4d.cli.run_patient_pipeline")
    @patch("a4d.config.settings")
    def test_skip_upload_calls_pipeline(self, mock_settings, mock_run_pipeline, tmp_path):
        mock_settings.data_root = tmp_path / "data"
        mock_settings.output_root = tmp_path / "output"
        mock_settings.project_id = "test-project"
        mock_settings.dataset = "test-dataset"
        mock_settings.max_workers = 4

        (tmp_path / "data").mkdir()
        (tmp_path / "output").mkdir()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.total_trackers = 0
        mock_result.successful_trackers = 0
        mock_result.failed_trackers = 0
        mock_result.tracker_results = []
        mock_result.tables = {}
        mock_run_pipeline.return_value = mock_result

        result = runner.invoke(
            app, ["run-pipeline", "--skip-download", "--skip-upload", "--skip-drive-download"]
        )

        mock_run_pipeline.assert_called_once()
        assert result.exit_code == 0

    @patch("a4d.cli.run_patient_pipeline")
    @patch("a4d.config.settings")
    def test_pipeline_failure_exits_nonzero(self, mock_settings, mock_run_pipeline, tmp_path):
        mock_settings.data_root = tmp_path / "data"
        mock_settings.output_root = tmp_path / "output"
        mock_settings.project_id = "test-project"
        mock_settings.dataset = "test-dataset"
        mock_settings.max_workers = 4

        (tmp_path / "data").mkdir()
        (tmp_path / "output").mkdir()

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.total_trackers = 1
        mock_result.successful_trackers = 0
        mock_result.failed_trackers = 1
        mock_result.tracker_results = [
            MagicMock(success=False, tracker_file=MagicMock(name="bad.xlsx"), error="Parse error")
        ]
        mock_result.tables = {}
        mock_run_pipeline.return_value = mock_result

        result = runner.invoke(
            app, ["run-pipeline", "--skip-download", "--skip-upload", "--skip-drive-download"]
        )

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# End-to-end test: process-patient with real dummy tracker
# ---------------------------------------------------------------------------


class TestProcessPatientE2E:
    """End-to-end test for process-patient using a synthetic tracker file."""

    def test_process_single_file_creates_outputs(self, dummy_tracker, tmp_path):
        """process-patient --file <dummy> --output <tmp> should produce parquet outputs."""
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "process-patient",
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
                "process-patient",
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
                "process-patient",
                "--file",
                str(dummy_tracker),
                "--output",
                str(output_dir),
                "--skip-tables",
            ],
        )

        assert result.exit_code == 0, f"Pipeline failed:\n{result.output}"

        tables_dir = output_dir / "tables"
        assert not tables_dir.exists() or not any(tables_dir.iterdir())

    def test_process_missing_file_exits_nonzero(self, tmp_path):
        """Passing a non-existent file should exit with error."""
        missing = tmp_path / "ghost.xlsx"
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            ["process-patient", "--file", str(missing), "--output", str(output_dir)],
        )

        assert result.exit_code == 1
