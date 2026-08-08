"""Load the previous run's manifest from BigQuery or a local parquet.

Source precedence:

1. BigQuery (``select_tracker_metadata``) — authoritative when running in
   Cloud Run with credentials available.
2. Local ``output_root/tables/tracker_metadata.parquet`` — fallback for
   developers without ``gcloud auth`` configured, or when BQ is unreachable.
3. Empty manifest — first-ever run, every tracker queues.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from loguru import logger

from a4d.state.manifest import Manifest, ManifestEntry


def _build_manifest(df: pl.DataFrame) -> Manifest:
    """Convert a (file_name, clinic_code, md5, complete) frame into a Manifest."""
    entries: dict[tuple[str, str], ManifestEntry] = {}
    for row in df.iter_rows(named=True):
        key = (row["clinic_code"], row["file_name"])
        entries[key] = ManifestEntry(md5=row["md5"], complete=bool(row["complete"]))
    return Manifest(entries=entries)


def load_previous_manifest(
    output_root: Path,
    *,
    prefer_bigquery: bool = True,
) -> Manifest:
    """Load the previous run's tracker manifest.

    Args:
        output_root: Pipeline output root; the local fallback reads
            ``output_root/tables/tracker_metadata.parquet`` from here.
        prefer_bigquery: If True, try BigQuery first. Set to False to skip the
            BQ lookup entirely (useful in tests or when running offline).

    Returns:
        A populated ``Manifest`` on success, or ``Manifest.empty()`` when no
        prior state is available. Never raises — every error path falls
        through with a logged warning.
    """
    if prefer_bigquery:
        # Imported here so the BigQuery client isn't constructed at module
        # import time. Keeps tests that patch the source module fast and
        # avoids touching gcloud creds when prefer_bigquery=False.
        from a4d.gcp.bigquery import select_tracker_metadata

        df = select_tracker_metadata()
        if df is not None and df.height > 0:
            logger.info(f"Loaded manifest from BigQuery ({df.height} rows)")
            return _build_manifest(df)

    local_parquet = output_root / "tables" / "tracker_metadata.parquet"
    if local_parquet.exists():
        try:
            df = pl.read_parquet(local_parquet)
            logger.info(f"Loaded manifest from local parquet ({df.height} rows): {local_parquet}")
            return _build_manifest(df)
        except Exception as e:
            logger.warning(f"Failed to read local manifest {local_parquet}: {e}")

    logger.info("No previous manifest available; treating every tracker as new")
    return Manifest.empty()
