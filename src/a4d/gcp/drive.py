"""Google Drive download utilities.

Replaces the R pipeline's googledrive::drive_download() calls.
Authentication uses Application Default Credentials (ADC), same as GCS/BigQuery.
"""

from pathlib import Path

import google.auth
import google.auth.transport.requests
from loguru import logger

# Google Drive file ID for clinic_data.xlsx
# R pipeline: googledrive::as_id("1HOxi0o9fTAoHySjW_M3F-09TRBnUITOzzxGx2HwRMAw")
CLINIC_DATA_FILE_ID = "1HOxi0o9fTAoHySjW_M3F-09TRBnUITOzzxGx2HwRMAw"

_DRIVE_API_URL = "https://www.googleapis.com/drive/v3/files"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def download_clinic_data(destination: Path) -> Path:
    """Download clinic_data.xlsx from Google Drive to the destination directory.

    Uses ADC with Drive readonly scope. In Cloud Run the service account must
    have 'Viewer' access to the file (or the shared drive it lives in).

    Args:
        destination: Directory to write clinic_data.xlsx into

    Returns:
        Path to the downloaded file

    Raises:
        requests.HTTPError: If the Drive API returns a non-2xx status
    """
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / "clinic_data.xlsx"

    logger.info(f"Downloading clinic_data.xlsx from Google Drive (file ID: {CLINIC_DATA_FILE_ID})")

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
    session = google.auth.transport.requests.AuthorizedSession(credentials)

    # clinic_data is a Google Sheets file — must use export endpoint, not alt=media.
    # R pipeline equivalent: googledrive::drive_download(..., type = "xlsx")
    url = (
        f"{_DRIVE_API_URL}/{CLINIC_DATA_FILE_ID}/export"
        f"?mimeType={_XLSX_MIME}&supportsAllDrives=true"
    )
    response = session.get(url, stream=True)
    if not response.ok:
        logger.error(f"Drive API error {response.status_code}: {response.text}")
    response.raise_for_status()

    bytes_written = 0
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
            f.write(chunk)
            bytes_written += len(chunk)

    size_kb = bytes_written / 1024
    logger.info(f"Downloaded clinic_data.xlsx: {size_kb:.1f} KB -> {output_path}")

    return output_path
