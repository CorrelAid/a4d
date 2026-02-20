"""Google Cloud Storage operations for tracker file download and output upload.

Replaces the R pipeline's `gsutil` CLI calls with the google-cloud-storage
Python client library.
"""

from pathlib import Path

from google.cloud import storage
from loguru import logger

from a4d.config import settings


def get_storage_client(project_id: str | None = None) -> storage.Client:
    """Create a GCS client.

    Authentication uses Application Default Credentials (ADC):
    - In Cloud Run / GCE: automatic via metadata server
    - Locally: via `gcloud auth application-default login`
    - In CI: via GOOGLE_APPLICATION_CREDENTIALS environment variable

    Args:
        project_id: GCP project ID (defaults to settings.project_id)

    Returns:
        Configured storage client
    """
    return storage.Client(project=project_id or settings.project_id)


def download_tracker_files(
    destination: Path,
    bucket_name: str | None = None,
    client: storage.Client | None = None,
) -> list[Path]:
    """Download tracker files from GCS bucket.

    Replaces R pipeline's `download_data()` function which used `gsutil -m cp -r`.
    Downloads all .xlsx files from the bucket, preserving directory structure.

    Args:
        destination: Local directory to download files to
        bucket_name: GCS bucket name (defaults to settings.download_bucket)
        client: Storage client (created if not provided)

    Returns:
        List of downloaded file paths
    """
    bucket_name = bucket_name or settings.download_bucket

    if client is None:
        client = get_storage_client()

    bucket = client.bucket(bucket_name)
    destination.mkdir(parents=True, exist_ok=True)

    logger.info(f"Downloading tracker files from gs://{bucket_name} to {destination}")

    downloaded: list[Path] = []
    blobs = list(bucket.list_blobs())
    logger.info(f"Found {len(blobs)} objects in bucket")

    for blob in blobs:
        # Skip directory markers
        if blob.name.endswith("/"):
            continue

        local_path = destination / blob.name
        local_path.parent.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Downloading: {blob.name}")
        blob.download_to_filename(str(local_path))
        downloaded.append(local_path)

    logger.info(f"Downloaded {len(downloaded)} files")
    return downloaded


def upload_output(
    source_dir: Path,
    bucket_name: str | None = None,
    prefix: str = "",
    client: storage.Client | None = None,
) -> list[str]:
    """Upload output directory to GCS bucket.

    Replaces R pipeline's `upload_data()` function which used `gsutil -m cp -r`.
    Uploads all files from the source directory, preserving directory structure.

    Args:
        source_dir: Local directory to upload
        bucket_name: GCS bucket name (defaults to settings.upload_bucket)
        prefix: Optional prefix for uploaded blob names
        client: Storage client (created if not provided)

    Returns:
        List of uploaded blob names

    Raises:
        FileNotFoundError: If source directory doesn't exist
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    bucket_name = bucket_name or settings.upload_bucket

    if client is None:
        client = get_storage_client()

    bucket = client.bucket(bucket_name)

    logger.info(f"Uploading {source_dir} to gs://{bucket_name}/{prefix}")

    uploaded: list[str] = []
    files = [f for f in source_dir.rglob("*") if f.is_file()]

    for file_path in files:
        relative_path = file_path.relative_to(source_dir)
        blob_name = f"{prefix}/{relative_path}" if prefix else str(relative_path)
        blob_name = blob_name.replace("\\", "/")  # Windows compatibility

        logger.debug(f"Uploading: {blob_name}")
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(file_path))
        uploaded.append(blob_name)

    logger.info(f"Uploaded {len(uploaded)} files to gs://{bucket_name}")
    return uploaded
