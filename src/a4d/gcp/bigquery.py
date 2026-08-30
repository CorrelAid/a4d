"""BigQuery table loading from parquet files.

Uses the google-cloud-bigquery Python client to load parquet files, with
per-table clustering configuration.
"""

from pathlib import Path

import polars as pl
from google.api_core.exceptions import GoogleAPIError, NotFound
from google.cloud import bigquery
from loguru import logger

from a4d.config import settings
from a4d.findings import FINDINGS_SCHEMA

# BigQuery rejects a CREATE with more than this many clustering fields, and it
# rejects it at load time, not at config time -- `findings` shipped with five
# and so had never once landed in the dataset. A unit test holds every entry
# below to this limit.
BIGQUERY_MAX_CLUSTERING_FIELDS = 4

# Clustering fields per table. These are the columns consumers filter on
# most, and clustering on them is what keeps a full-corpus query cheap.
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
    "logs": ["level", "file_name", "function", "module"],
    # `column` was the fifth field and is dropped: clustering prunes on a
    # prefix, so the last field of five was doing the least work anyway, and it
    # is the most granular of them -- consumers filter by tracker, by what to
    # do about it, and by problem code long before they filter by column name.
    "findings": ["file_name", "category", "error_code", "patient_id"],
    "tracker_metadata": ["file_name", "clinic_code"],
}

# Groups of BigQuery table names selectable via `a4d upload tables --only <group>`.
TABLE_GROUPS: dict[str, set[str]] = {
    "patient": {"patient_data_static", "patient_data_monthly", "patient_data_annual"},
    "product": {"product_data"},
    "clinic": {"clinic_data_static"},
    "logs": {"logs"},
    "findings": {"findings"},
    "metadata": {"tracker_metadata"},
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
    "table_findings.parquet": "findings",
    "tracker_metadata.parquet": "tracker_metadata",
}


def published_table_names() -> list[str]:
    """The BigQuery tables a full pipeline run deletes and recreates.

    Derived from ``PARQUET_TO_TABLE`` so that the pre-run backup snapshot and
    the post-run verification cannot drift off what is actually published --
    both kept their own hand-typed copy until one of them was still
    snapshotting the retired ``errors`` table and neither covered ``findings``.

    Returns:
        Table names, sorted, so callers render them in a stable order.
    """
    return sorted(PARQUET_TO_TABLE.values())


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

    1. Optionally deletes the existing table (replace=True by default)
    2. Loads the parquet file with clustering fields

    Args:
        parquet_path: Path to the parquet file to load
        table_name: BigQuery table name (e.g., "patient_data_monthly")
        client: BigQuery client (created if not provided)
        dataset: Dataset name (defaults to settings.dataset)
        project_id: GCP project ID (defaults to settings.project_id)
        replace: If True, deletes and recreates the table (default)

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

    # WRITE_TRUNCATE preserves the existing clustering and schema, so a
    # deliberate change to either would silently not take effect -- delete
    # first instead.
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
    only_tables: set[str] | None = None,
) -> dict[str, bigquery.LoadJob]:
    """Load pipeline output tables into BigQuery.

    Scans the tables directory for known parquet files and loads each one
    into the corresponding BigQuery table.

    Args:
        tables_dir: Directory containing parquet table files (e.g., output/tables/)
        client: BigQuery client (created if not provided)
        dataset: Dataset name (defaults to settings.dataset)
        project_id: GCP project ID (defaults to settings.project_id)
        replace: If True, replaces existing tables
        only_tables: If set, restrict loading to these BigQuery table names
            (see TABLE_GROUPS for the named groups CLI callers select from).
            None loads every known table.

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
    failures: dict[str, Exception] = {}

    for parquet_name, table_name in PARQUET_TO_TABLE.items():
        if only_tables is not None and table_name not in only_tables:
            continue
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
            except Exception as e:
                # Collected rather than raised here, so one unloadable table
                # does not strand the ones after it -- but the run must not
                # then report success, which is exactly what it used to do.
                logger.exception(f"Failed to load table: {table_name}")
                failures[table_name] = e
        else:
            logger.warning(f"Table file not found, skipping: {parquet_name}")

    considered = (
        len(PARQUET_TO_TABLE)
        if only_tables is None
        else sum(1 for t in PARQUET_TO_TABLE.values() if t in only_tables)
    )
    logger.info(f"Successfully loaded {len(results)}/{considered} tables")

    if failures:
        detail = "; ".join(f"{table}: {error}" for table, error in sorted(failures.items()))
        raise RuntimeError(f"Failed to load {len(failures)} BigQuery table(s) -- {detail}")

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
                rows = list(
                    client.query(f"SELECT file_name, clinic_code, md5 FROM `{table_ref}`").result()
                )
                fallback_schema = {k: v for k, v in full_schema.items() if k != "complete"}
                data = {col: [r[col] for r in rows] for col in fallback_schema}
                df = pl.DataFrame(data, schema=fallback_schema)
                return df.with_columns(pl.lit(False).alias("complete"))
            except GoogleAPIError as retry_err:
                logger.warning(f"BigQuery schema-fallback query failed: {retry_err}")
                return None
        logger.warning(f"BigQuery query failed for {table_ref}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error querying {table_ref}: {e}")
        return None


def select_findings(
    client: bigquery.Client | None = None,
    dataset: str | None = None,
    project_id: str | None = None,
) -> pl.DataFrame | None:
    """Read the published ``findings`` table, for reporting on a deployed run.

    Returns ``None`` rather than raising on an unavailable client, a missing
    table or any API error, so ``a4d report findings --from-bigquery`` can say
    what went wrong instead of dying with a traceback. The local parquet is the
    default source precisely because this path needs credentials.

    Args:
        client: An existing BigQuery client, or None to build one
        dataset: Dataset holding the table (default: from config)
        project_id: GCP project (default: from config)

    Returns:
        The findings table, or None if it could not be read
    """
    project_id = project_id or settings.project_id
    dataset = dataset or settings.dataset

    if client is None:
        try:
            client = get_bigquery_client(project_id)
        except Exception as e:
            logger.warning(f"BigQuery client unavailable, cannot read findings: {e}")
            return None

    table_ref = f"{project_id}.{dataset}.findings"
    columns = list(FINDINGS_SCHEMA)

    try:
        rows = list(client.query(f"SELECT {', '.join(columns)} FROM `{table_ref}`").result())
    except NotFound:
        logger.warning(f"BigQuery table not found: {table_ref}")
        return None
    except GoogleAPIError as e:
        logger.warning(f"BigQuery query failed for {table_ref}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error querying {table_ref}: {e}")
        return None

    data = {column: [row[column] for row in rows] for column in columns}
    return pl.DataFrame(data, schema=FINDINGS_SCHEMA)
