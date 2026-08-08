"""Tests for Google Drive download module."""

from unittest.mock import MagicMock, patch

import pytest

from a4d.gcp.drive import CLINIC_DATA_FILE_ID, download_clinic_data


class TestDownloadClinicData:
    """Tests for download_clinic_data."""

    @patch("a4d.gcp.drive.google.auth.default")
    @patch("a4d.gcp.drive.google.auth.transport.requests.AuthorizedSession")
    def test_downloads_to_destination(self, mock_session_cls, mock_auth_default, tmp_path):
        mock_auth_default.return_value = (MagicMock(), "project")
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"data1", b"data2"]
        mock_session.get.return_value = mock_response

        result = download_clinic_data(tmp_path)

        assert result == tmp_path / "clinic_data.xlsx"
        assert result.exists()
        assert result.read_bytes() == b"data1data2"

    @patch("a4d.gcp.drive.google.auth.default")
    @patch("a4d.gcp.drive.google.auth.transport.requests.AuthorizedSession")
    def test_uses_correct_file_id(self, mock_session_cls, mock_auth_default, tmp_path):
        mock_auth_default.return_value = (MagicMock(), "project")
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"xlsx"]
        mock_session.get.return_value = mock_response

        download_clinic_data(tmp_path)

        call_url = mock_session.get.call_args[0][0]
        assert CLINIC_DATA_FILE_ID in call_url
        assert "/export" in call_url
        assert "mimeType=" in call_url

    @patch("a4d.gcp.drive.google.auth.default")
    @patch("a4d.gcp.drive.google.auth.transport.requests.AuthorizedSession")
    def test_uses_drive_readonly_scope(self, mock_session_cls, mock_auth_default, tmp_path):
        mock_auth_default.return_value = (MagicMock(), "project")
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"xlsx"]
        mock_session.get.return_value = mock_response

        download_clinic_data(tmp_path)

        scopes = mock_auth_default.call_args[1]["scopes"]
        assert any("drive" in s for s in scopes)

    @patch("a4d.gcp.drive.google.auth.default")
    @patch("a4d.gcp.drive.google.auth.transport.requests.AuthorizedSession")
    def test_raises_on_http_error(self, mock_session_cls, mock_auth_default, tmp_path):
        import requests as req

        mock_auth_default.return_value = (MagicMock(), "project")
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.HTTPError("403 Forbidden")
        mock_session.get.return_value = mock_response

        with pytest.raises(req.HTTPError):
            download_clinic_data(tmp_path)

    @patch("a4d.gcp.drive.google.auth.default")
    @patch("a4d.gcp.drive.google.auth.transport.requests.AuthorizedSession")
    def test_creates_destination_directory(self, mock_session_cls, mock_auth_default, tmp_path):
        mock_auth_default.return_value = (MagicMock(), "project")
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"xlsx"]
        mock_session.get.return_value = mock_response

        dest = tmp_path / "new" / "subdir"
        download_clinic_data(dest)

        assert dest.exists()
