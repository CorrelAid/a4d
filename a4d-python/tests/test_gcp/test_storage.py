"""Tests for Google Cloud Storage module."""

from unittest.mock import MagicMock, patch

import pytest

from a4d.gcp.storage import download_tracker_files, upload_output


class TestDownloadTrackerFiles:
    """Test downloading tracker files from GCS."""

    @patch("a4d.gcp.storage.get_storage_client")
    def test_downloads_files(self, mock_get_client, tmp_path):
        destination = tmp_path / "trackers"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        # Simulate blobs in bucket
        blob1 = MagicMock()
        blob1.name = "2024/tracker1.xlsx"
        blob2 = MagicMock()
        blob2.name = "2024/tracker2.xlsx"
        mock_bucket.list_blobs.return_value = [blob1, blob2]

        result = download_tracker_files(destination, client=mock_client)

        assert len(result) == 2
        assert blob1.download_to_filename.called
        assert blob2.download_to_filename.called

    @patch("a4d.gcp.storage.get_storage_client")
    def test_skips_directory_markers(self, mock_get_client, tmp_path):
        destination = tmp_path / "trackers"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        blob_dir = MagicMock()
        blob_dir.name = "2024/"
        blob_file = MagicMock()
        blob_file.name = "2024/tracker.xlsx"
        mock_bucket.list_blobs.return_value = [blob_dir, blob_file]

        result = download_tracker_files(destination, client=mock_client)

        assert len(result) == 1
        assert not blob_dir.download_to_filename.called

    @patch("a4d.gcp.storage.get_storage_client")
    def test_creates_destination_directory(self, mock_get_client, tmp_path):
        destination = tmp_path / "new" / "dir"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.return_value = []

        download_tracker_files(destination, client=mock_client)

        assert destination.exists()


class TestUploadOutput:
    """Test uploading output to GCS."""

    def test_raises_if_source_missing(self, tmp_path):
        missing_dir = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError, match="Source directory not found"):
            upload_output(missing_dir)

    @patch("a4d.gcp.storage.get_storage_client")
    def test_uploads_files(self, mock_get_client, tmp_path):
        source = tmp_path / "output"
        source.mkdir()
        (source / "tables").mkdir()
        (source / "tables" / "data.parquet").write_bytes(b"data")
        (source / "logs.txt").write_text("log")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        result = upload_output(source, client=mock_client)

        assert len(result) == 2
        assert mock_blob.upload_from_filename.call_count == 2

    @patch("a4d.gcp.storage.get_storage_client")
    def test_upload_with_prefix(self, mock_get_client, tmp_path):
        source = tmp_path / "output"
        source.mkdir()
        (source / "file.parquet").write_bytes(b"data")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        result = upload_output(source, prefix="2024-01", client=mock_client)

        assert len(result) == 1
        assert result[0] == "2024-01/file.parquet"
