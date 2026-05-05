"""BigQuery table loading from parquet files.

Replaces the R pipeline's `ingest_data()` function which used the `bq` CLI tool.
Uses the google-cloud-bigquery Python client for loading parquet files with
clustering configuration matching the R pipeline.
"""

from pathlib import Path

import polars as pl
from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPIError, NotFound
from loguru import logger

from a4d.config import settings

# Table configurations matching the R pipeline's clustering fields.
# Each table maps to the clustering fields used for optimal query performance.
TABLE_CONFIGS: dict[str, list[str]] = {
    "patient_data_monthly": ["clinic_id", "patient_id", "tracker_date"],
    "patient_data_annual": ["patient_id", "tracker_date"],
    "patient_data_static": ["clinic_id", "patient_id", "tracker_date"],
    "product_data": [
        "clinic_id",
        "product_released_to",
        "product_table_year",
        "product_table_month",
    ],
    "clinic_data_static": ["clinic_id"],
    "logs": ["level", "error_code", "file_name", "function"],
    "tracker_metadata": ["file_name", "clinic_code"],
}

# Maps the pipeline output file names to BigQuery table names.
# Note: table_logs.parquet uses this name from create_table_logs() in tables/logs.py.
PARQUET_TO_TABLE: dict[str, str] = {
    "patient_data_static.parquet": "patient_data_static",
    "patient_data_monthly.parquet": "patient_data_monthly",
    "patient_data_annual.parquet": "patient_data_annual",
    "product_data.parquet": "product_data",
    "clinic_data_static.parquet": "clinic_data_static",
    "table_logs.parquet": "logs",
    "tracker_metadata.parquet": "tracker_metadata",
}


def get_bigquery_client(project_id: str | None = None) -> bigquery.Client:
    """Create a BigQuery client.

    Authentication uses Application Default Credentials (ADC):
    - In Cloud Run / GCE: automatic via metadata server
    - Locally: via `gcloud auth application-default login`
    - In CI: via GOOGLE_APPLICATION_CREDENTIALS environment variable

    Args:
        project_id: GCP project ID (defaults to settings.project_id)

    Returns:
        Configured BigQuery client
    """
    return bigquery.Client(project=project_id or settings.project_id)


def load_table(
    parquet_path: Path,
    table_name: str,
    client: bigquery.Client | None = None,
    dataset: str | None = None,
    project_id: str | None = None,
    replace: bool = True,
) -> bigquery.LoadJob:
    """Load a parquet file into a BigQuery table.

    Replicates the R pipeline's `ingest_data()` function:
    1. Optionally deletes the existing table (replace=True, matching R's delete=T default)
    2. Loads the parquet file with clustering fields

    Args:
        parquet_path: Path to the parquet file to load
        table_name: BigQuery table name (e.g., "patient_data_monthly")
        client: BigQuery client (created if not provided)
        dataset: Dataset name (defaults to settings.dataset)
        project_id: GCP project ID (defaults to settings.project_id)
        replace: If True, replaces the existing table (default matches R pipeline)

    Returns:
        Completed LoadJob

    Raises:
        FileNotFoundError: If parquet file doesn't exist
        ValueError: If table_name is not in TABLE_CONFIGS
        google.api_core.exceptions.GoogleAPIError: On BigQuery API errors
    """
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    dataset = dataset or settings.dataset
    project_id = project_id or settings.project_id

    if client is None:
        client = get_bigquery_client(project_id)

    table_ref = f"{project_id}.{dataset}.{table_name}"
    logger.info(f"Loading {parquet_path.name} → {table_ref}")

    # WRITE_TRUNCATE preserves existing clustering, so deleting first ensures
    # any schema or clustering changes (e.g. from R→Python migration) take effect.
    if replace:
        try:
            client.delete_table(table_ref)
            logger.info(f"Deleted existing table {table_ref} for fresh creation")
        except NotFound:
            pass

    # Configure the load job
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=(
            bigquery.WriteDisposition.WRITE_TRUNCATE
            if replace
            else bigquery.WriteDisposition.WRITE_APPEND
        ),
    )

    # Add clustering if configured for this table
    clustering_fields = TABLE_CONFIGS.get(table_name)
    if clustering_fields:
        job_config.clustering_fields = clustering_fields
        logger.info(f"Clustering fields: {clustering_fields}")

    # Load the parquet file
    with open(parquet_path, "rb") as f:
        load_job = client.load_table_from_file(f, table_ref, job_config=job_config)

    # Wait for completion
    load_job.result()

    logger.info(
        f"Loaded {load_job.output_rows} rows into {table_ref} "
        f"({parquet_path.stat().st_size / 1024 / 1024:.2f} MB)"
    )
    return load_job


def load_pipeline_tables(
    tables_dir: Path,
    client: bigquery.Client | None = None,
    dataset: str | None = None,
    project_id: str | None = None,
    replace: bool = True,
) -> dict[str, bigquery.LoadJob]:
    """Load all pipeline output tables into BigQuery.

    Scans the tables directory for known parquet files and loads each one
    into the corresponding BigQuery table.

    Args:
        tables_dir: Directory containing parquet table files (e.g., output/tables/)
        client: BigQuery client (created if not provided)
        dataset: Dataset name (defaults to settings.dataset)
        project_id: GCP project ID (defaults to settings.project_id)
        replace: If True, replaces existing tables

    Returns:
        Dictionary mapping table name to completed LoadJob

    Raises:
        FileNotFoundError: If tables_dir doesn't exist
    """
    if not tables_dir.exists():
        raise FileNotFoundError(f"Tables directory not found: {tables_dir}")

    if client is None:
        project_id = project_id or settings.project_id
        client = get_bigquery_client(project_id)

    logger.info(f"Loading pipeline tables from: {tables_dir}")

    results: dict[str, bigquery.LoadJob] = {}

    for parquet_name, table_name in PARQUET_TO_TABLE.items():
        parquet_path = tables_dir / parquet_name
        if parquet_path.exists():
            try:
                job = load_table(
                    parquet_path=parquet_path,
                    table_name=table_name,
                    client=client,
                    dataset=dataset,
                    project_id=project_id,
                    replace=replace,
                )
                results[table_name] = job
            except Exception:
                logger.exception(f"Failed to load table: {table_name}")
        else:
            logger.warning(f"Table file not found, skipping: {parquet_name}")

    logger.info(f"Successfully loaded {len(results)}/{len(PARQUET_TO_TABLE)} tables")
    return results


def select_tracker_metadata(
    client: bigquery.Client | None = None,
    dataset: str | None = None,
    project_id: str | None = None,
) -> pl.DataFrame | None:
    """Read ``file_name, clinic_code, md5, complete`` from BigQuery.

    Used by ``a4d.state.source.load_previous_manifest`` to query the previous
    run's tracker manifest for incremental processing.

    Returns ``None`` (rather than raising) on:

    * authentication failure (``DefaultCredentialsError``) — caller falls back
      to local parquet,
    * missing table (``NotFound``) — first-ever run, no manifest yet,
    * any other ``GoogleAPIError`` — network issues etc., fall back rather
      than block the pipeline.

    Schema fallback: if the BQ table predates the ``complete`` column being
    published, the query is retried without it and ``complete`` is synthesised
    as ``False`` for every row — forces a full reprocess, which is the safe
    default when manifest provenance is uncertain.
    """
    project_id = project_id or settings.project_id
    dataset = dataset or settings.dataset

    if client is None:
        try:
            client = get_bigquery_client(project_id)
        except Exception as e:
            logger.warning(f"BigQuery client unavailable, skipping metadata query: {e}")
            return None

    table_ref = f"{project_id}.{dataset}.tracker_metadata"
    full_query = f"SELECT file_name, clinic_code, md5, complete FROM `{table_ref}`"

    full_schema = {
        "file_name": pl.Utf8,
        "clinic_code": pl.Utf8,
        "md5": pl.Utf8,
        "complete": pl.Boolean,
    }

    try:
        rows = list(client.query(full_query).result())
        data = {col: [r[col] for r in rows] for col in full_schema}
        return pl.DataFrame(data, schema=full_schema)
    except NotFound:
        logger.info(f"BigQuery table not found, no previous manifest: {table_ref}")
        return None
    except GoogleAPIError as e:
        # Schema fallback: retry without `complete` if the column is missing
        # in the deployed table. The synthesised complete=False forces a
        # full reprocess.
        message = str(e).lower()
        if "complete" in message and ("unrecognized name" in message or "not found" in message):
            logger.warning(
                f"BigQuery {table_ref} missing 'complete' column; "
                "retrying without it and forcing full reprocess"
            )
            try:
                rows = list(client.query(
                    f"SELECT file_name, clinic_code, md5 FROM `{table_ref}`"
                ).result())
                fallback_schema = {k: v for k, v in full_schema.items() if k != "complete"}
                data = {col: [r[col] for r in rows] for col in fallback_schema}
                df = pl.DataFrame(data, schema=fallback_schema)
                return df.with_columns(pl.lit(False).alias("complete"))
            except GoogleAPIError as retry_err:
                logger.warning(
                    f"BigQuery schema-fallback query failed: {retry_err}"
                )
                return None
        logger.warning(f"BigQuery query failed for {table_ref}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error querying {table_ref}: {e}")
        return None
