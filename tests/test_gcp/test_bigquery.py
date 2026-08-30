"""Tests for BigQuery loading module."""

from unittest.mock import MagicMock, patch

import pytest

from a4d.gcp.bigquery import (
    PARQUET_TO_TABLE,
    TABLE_CONFIGS,
    load_pipeline_tables,
    load_table,
)


def _get_job_config(mock_client):
    """Extract job_config from mock client's load_table_from_file call."""
    return mock_client.load_table_from_file.call_args.kwargs["job_config"]


class TestTableConfigs:
    """Every published table has clustering fields declared."""

    def test_patient_data_monthly_clustering(self):
        assert TABLE_CONFIGS["patient_data_monthly"] == [
            "clinic_id",
            "patient_id",
            "tracker_date",
        ]

    def test_patient_data_annual_clustering(self):
        assert TABLE_CONFIGS["patient_data_annual"] == ["patient_id", "tracker_date"]

    def test_patient_data_static_clustering(self):
        assert TABLE_CONFIGS["patient_data_static"] == [
            "clinic_id",
            "patient_id",
            "tracker_date",
        ]

    def test_all_pipeline_tables_have_configs(self):
        for table_name in PARQUET_TO_TABLE.values():
            assert table_name in TABLE_CONFIGS, f"Missing config for {table_name}"


class TestLoadTable:
    """Test loading a single parquet file to BigQuery."""

    def test_raises_file_not_found(self, tmp_path):
        missing_file = tmp_path / "missing.parquet"
        with pytest.raises(FileNotFoundError, match="Parquet file not found"):
            load_table(missing_file, "patient_data_monthly")

    @patch("a4d.gcp.bigquery.get_bigquery_client")
    def test_load_table_with_replace(self, mock_get_client, tmp_path):
        parquet_file = tmp_path / "test.parquet"
        parquet_file.write_bytes(b"fake parquet data")

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.output_rows = 100
        mock_client.load_table_from_file.return_value = mock_job
        mock_get_client.return_value = mock_client

        load_table(parquet_file, "patient_data_monthly", client=mock_client)

        mock_client.load_table_from_file.assert_called_once()
        job_config = _get_job_config(mock_client)
        assert job_config.clustering_fields == ["clinic_id", "patient_id", "tracker_date"]
        mock_job.result.assert_called_once()

    @patch("a4d.gcp.bigquery.get_bigquery_client")
    def test_load_table_with_append(self, mock_get_client, tmp_path):
        parquet_file = tmp_path / "test.parquet"
        parquet_file.write_bytes(b"fake parquet data")

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.output_rows = 50
        mock_client.load_table_from_file.return_value = mock_job

        load_table(parquet_file, "patient_data_monthly", client=mock_client, replace=False)

        job_config = _get_job_config(mock_client)
        assert job_config.write_disposition == "WRITE_APPEND"

    @patch("a4d.gcp.bigquery.get_bigquery_client")
    def test_load_table_correct_table_ref(self, mock_get_client, tmp_path):
        parquet_file = tmp_path / "test.parquet"
        parquet_file.write_bytes(b"fake parquet data")

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.output_rows = 10
        mock_client.load_table_from_file.return_value = mock_job

        load_table(
            parquet_file,
            "patient_data_static",
            client=mock_client,
            dataset="test_dataset",
            project_id="test_project",
        )

        table_ref = mock_client.load_table_from_file.call_args.args[1]
        assert table_ref == "test_project.test_dataset.patient_data_static"


class TestLoadPipelineTables:
    """Test loading all pipeline tables."""

    def test_raises_if_dir_missing(self, tmp_path):
        missing_dir = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError, match="Tables directory not found"):
            load_pipeline_tables(missing_dir)

    @patch("a4d.gcp.bigquery.load_table")
    @patch("a4d.gcp.bigquery.get_bigquery_client")
    def test_loads_existing_tables(self, mock_get_client, mock_load, tmp_path):
        tables_dir = tmp_path / "tables"
        tables_dir.mkdir()

        # Create some table files
        (tables_dir / "patient_data_static.parquet").write_bytes(b"data")
        (tables_dir / "patient_data_monthly.parquet").write_bytes(b"data")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_load.return_value = MagicMock()

        results = load_pipeline_tables(tables_dir, client=mock_client)

        assert mock_load.call_count == 2
        assert "patient_data_static" in results
        assert "patient_data_monthly" in results

    @patch("a4d.gcp.bigquery.load_table")
    @patch("a4d.gcp.bigquery.get_bigquery_client")
    def test_skips_missing_tables(self, mock_get_client, mock_load, tmp_path):
        tables_dir = tmp_path / "tables"
        tables_dir.mkdir()

        # Only create one table file
        (tables_dir / "patient_data_static.parquet").write_bytes(b"data")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_load.return_value = MagicMock()

        results = load_pipeline_tables(tables_dir, client=mock_client)

        assert mock_load.call_count == 1
        assert "patient_data_static" in results
        assert "patient_data_monthly" not in results

    @patch("a4d.gcp.bigquery.load_table")
    @patch("a4d.gcp.bigquery.get_bigquery_client")
    def test_continues_on_single_table_failure(self, mock_get_client, mock_load, tmp_path):
        tables_dir = tmp_path / "tables"
        tables_dir.mkdir()

        (tables_dir / "patient_data_static.parquet").write_bytes(b"data")
        (tables_dir / "patient_data_monthly.parquet").write_bytes(b"data")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # First call succeeds, second fails
        mock_load.side_effect = [MagicMock(), Exception("API error")]

        results = load_pipeline_tables(tables_dir, client=mock_client)

        # Should have one success despite the failure
        assert len(results) == 1


class TestPublishedTableNames:
    """The names the pipeline publishes, derived once and read everywhere.

    `just backup-bq` and the post-run verification both used to keep their own
    hand-typed copy of this list, and both drifted off it.
    """

    def test_matches_the_parquet_to_table_mapping(self):
        from a4d.gcp.bigquery import PARQUET_TO_TABLE, published_table_names

        assert set(published_table_names()) == set(PARQUET_TO_TABLE.values())

    def test_is_sorted_so_callers_get_a_stable_order(self):
        from a4d.gcp.bigquery import published_table_names

        assert published_table_names() == sorted(published_table_names())
