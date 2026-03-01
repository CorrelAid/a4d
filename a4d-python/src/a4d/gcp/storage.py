"""Google Cloud Storage operations for tracker file download and output upload.

Replaces the R pipeline's `gsutil` CLI calls with the google-cloud-storage
Python client library.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.cloud import storage
from loguru import logger

from a4d.config import settings

_GCS_WORKERS = 16  # parallel connections; GCS supports many concurrent requests


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


def _download_blob(blob: storage.Blob, destination: Path) -> Path | None:
    """Download a single blob, skipping if the local file is already current.

    Uses blob.size (available from list_blobs metadata at no extra cost) to
    detect unchanged files without reading the file content.

    Returns the local path if downloaded, None if skipped.
    """
    local_path = destination / blob.name

    if local_path.exists() and local_path.stat().st_size == blob.size:
        logger.debug(f"Skipping (unchanged): {blob.name}")
        return None

    local_path.parent.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Downloading: {blob.name}")
    blob.download_to_filename(str(local_path))
    return local_path


def download_tracker_files(
    destination: Path,
    bucket_name: str | None = None,
    client: storage.Client | None = None,
) -> list[Path]:
    """Download tracker files from GCS bucket.

    Downloads in parallel and skips files whose local size already matches
    the blob size (equivalent to gsutil -m cp -n).

    Args:
        destination: Local directory to download files to
        bucket_name: GCS bucket name (defaults to settings.download_bucket)
        client: Storage client (created if not provided)

    Returns:
        List of downloaded file paths (excludes skipped files)
    """
    bucket_name = bucket_name or settings.download_bucket

    if client is None:
        client = get_storage_client()

    bucket = client.bucket(bucket_name)
    destination.mkdir(parents=True, exist_ok=True)

    logger.info(f"Downloading tracker files from gs://{bucket_name} to {destination}")

    blobs = [b for b in bucket.list_blobs() if not b.name.endswith("/")]
    logger.info(f"Found {len(blobs)} objects in bucket")

    downloaded: list[Path] = []

    with ThreadPoolExecutor(max_workers=_GCS_WORKERS) as executor:
        futures = {executor.submit(_download_blob, blob, destination): blob for blob in blobs}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    downloaded.append(result)
            except Exception:
                blob = futures[future]
                logger.error(f"Failed to download: {blob.name}")

    skipped = len(blobs) - len(downloaded)
    logger.info(f"Downloaded {len(downloaded)} files, skipped {skipped} unchanged")
    return downloaded


def _upload_file(bucket: storage.Bucket, file_path: Path, blob_name: str) -> str:
    """Upload a single file to GCS."""
    logger.debug(f"Uploading: {blob_name}")
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(file_path))
    return blob_name


def upload_output(
    source_dir: Path,
    bucket_name: str | None = None,
    prefix: str = "",
    client: storage.Client | None = None,
) -> list[str]:
    """Upload output directory to GCS bucket in parallel.

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

    files = [f for f in source_dir.rglob("*") if f.is_file()]

    def _blob_name(file_path: Path) -> str:
        relative = file_path.relative_to(source_dir)
        name = f"{prefix}/{relative}" if prefix else str(relative)
        return name.replace("\\", "/")

    uploaded: list[str] = []

    with ThreadPoolExecutor(max_workers=_GCS_WORKERS) as executor:
        futures = {executor.submit(_upload_file, bucket, f, _blob_name(f)): f for f in files}
        for future in as_completed(futures):
            try:
                uploaded.append(future.result())
            except Exception:
                file_path = futures[future]
                logger.error(f"Failed to upload: {file_path}")

    logger.info(f"Uploaded {len(uploaded)} files to gs://{bucket_name}")
    return uploaded
