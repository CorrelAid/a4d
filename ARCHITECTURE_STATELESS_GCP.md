# Stateless Pipeline Architecture for GCP

## The Problem with SQLite

**Cloud Run / Cloud Functions are stateless**:
- Each container run starts fresh
- No local filesystem persists between runs
- SQLite database would be lost after each run

**Solution**: Use BigQuery metadata table as state store (you already have this!)

## Your Existing Metadata Table

From `run_script_5_create_metadata_table.R`, you already create a metadata table with:
- File name
- Clinic code
- Processing timestamp
- File hash (or can add this)
- Row counts, error counts, etc.

This table is **perfect** for state tracking because:
- ✅ Persists in BigQuery (survives container restarts)
- ✅ Already being created
- ✅ Queryable for incremental logic
- ✅ Useful for dashboards/analysis
- ✅ Single source of truth

## Architecture: BigQuery as State Store

```
Pipeline Run:
├─ 1. Download data from GCS
├─ 2. Query BigQuery metadata table → get previous file hashes
├─ 3. Compare current files with previous hashes
├─ 4. Process only changed/new files (in parallel)
├─ 5. Create final tables
├─ 6. Update metadata table with new hashes/stats
└─ 7. Upload all to BigQuery
```

## Implementation

### Metadata Schema

**BigQuery Table: `tracker_metadata`**
```sql
CREATE TABLE tracker.tracker_metadata (
  file_name STRING NOT NULL,
  file_path STRING,
  file_hash STRING NOT NULL,           -- MD5 hash for change detection
  clinic_code STRING,
  tracker_year INT64,
  tracker_month INT64,

  -- Processing info
  last_processed TIMESTAMP NOT NULL,
  processing_time_seconds FLOAT64,
  status STRING NOT NULL,               -- 'success', 'failed', 'processing'

  -- Data stats
  patient_count INT64,
  row_count INT64,
  error_count INT64,

  -- Error details
  error_message STRING,

  -- Audit
  pipeline_version STRING,
  processed_by STRING
);
```

### State Manager with BigQuery

**src/a4d/state/bigquery_state.py**:
```python
import hashlib
import polars as pl
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from google.cloud import bigquery
from a4d.config import settings
from a4d.logging import get_logger

logger = get_logger(__name__)


class BigQueryStateManager:
    """Manage processing state using BigQuery metadata table."""

    def __init__(self, project_id: str, dataset: str, table: str = "tracker_metadata"):
        self.client = bigquery.Client(project=project_id)
        self.table_id = f"{project_id}.{dataset}.{table}"
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create metadata table if it doesn't exist."""
        schema = [
            bigquery.SchemaField("file_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("file_path", "STRING"),
            bigquery.SchemaField("file_hash", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("clinic_code", "STRING"),
            bigquery.SchemaField("tracker_year", "INT64"),
            bigquery.SchemaField("tracker_month", "INT64"),
            bigquery.SchemaField("last_processed", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("processing_time_seconds", "FLOAT64"),
            bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("patient_count", "INT64"),
            bigquery.SchemaField("row_count", "INT64"),
            bigquery.SchemaField("error_count", "INT64"),
            bigquery.SchemaField("error_message", "STRING"),
            bigquery.SchemaField("pipeline_version", "STRING"),
            bigquery.SchemaField("processed_by", "STRING"),
        ]

        table = bigquery.Table(self.table_id, schema=schema)
        try:
            self.client.create_table(table, exists_ok=True)
            logger.info("Metadata table ready", table=self.table_id)
        except Exception as e:
            logger.warning("Could not create table", error=str(e))

    def get_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file."""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_previous_state(self) -> pl.DataFrame:
        """
        Query BigQuery for previous processing state.

        Returns Polars DataFrame with previous file hashes and status.
        """
        query = f"""
        SELECT
            file_name,
            file_hash,
            status,
            last_processed,
            patient_count,
            row_count,
            error_count
        FROM `{self.table_id}`
        WHERE last_processed = (
            SELECT MAX(last_processed)
            FROM `{self.table_id}` AS inner_table
            WHERE inner_table.file_name = {self.table_id}.file_name
        )
        """

        try:
            # Query and convert to Polars
            df_pandas = self.client.query(query).to_dataframe()

            if len(df_pandas) == 0:
                # No previous state, return empty DataFrame with schema
                return pl.DataFrame(schema={
                    "file_name": pl.Utf8,
                    "file_hash": pl.Utf8,
                    "status": pl.Utf8,
                })

            df = pl.from_pandas(df_pandas)
            logger.info("Retrieved previous state", file_count=len(df))
            return df

        except Exception as e:
            logger.warning("Could not retrieve previous state", error=str(e))
            # Return empty DataFrame if table doesn't exist yet
            return pl.DataFrame(schema={
                "file_name": pl.Utf8,
                "file_hash": pl.Utf8,
                "status": pl.Utf8,
            })

    def get_files_to_process(
        self,
        tracker_files: List[Path],
        force: bool = False,
    ) -> List[Path]:
        """
        Determine which files need processing.

        A file needs processing if:
        - It's new (not in previous state)
        - Its hash changed (content modified)
        - Previous processing failed
        - Force flag is set
        """
        if force:
            logger.info("Force mode: processing all files", count=len(tracker_files))
            return tracker_files

        # Get previous state from BigQuery
        previous_state = self.get_previous_state()

        if len(previous_state) == 0:
            logger.info("No previous state: processing all files", count=len(tracker_files))
            return tracker_files

        # Create lookup dict: file_name -> (hash, status)
        previous_lookup = {
            row["file_name"]: (row["file_hash"], row["status"])
            for row in previous_state.iter_rows(named=True)
        }

        # Determine which files to process
        files_to_process = []

        for file_path in tracker_files:
            file_name = file_path.name
            current_hash = self.get_file_hash(file_path)

            if file_name not in previous_lookup:
                # New file
                logger.debug("New file", file=file_name)
                files_to_process.append(file_path)
            else:
                previous_hash, status = previous_lookup[file_name]

                if current_hash != previous_hash:
                    # File changed
                    logger.debug("File changed", file=file_name)
                    files_to_process.append(file_path)
                elif status == "failed":
                    # Previous processing failed, retry
                    logger.debug("Previous failure, retrying", file=file_name)
                    files_to_process.append(file_path)
                else:
                    # Unchanged and successful
                    logger.debug("File unchanged", file=file_name)

        logger.info(
            "Incremental processing",
            total=len(tracker_files),
            to_process=len(files_to_process),
            skipped=len(tracker_files) - len(files_to_process),
        )

        return files_to_process

    def create_metadata_record(
        self,
        file_path: Path,
        clinic_code: Optional[str],
        tracker_year: Optional[int],
        tracker_month: Optional[int],
        status: str,
        patient_count: int = 0,
        row_count: int = 0,
        error_count: int = 0,
        processing_time: float = 0.0,
        error_message: Optional[str] = None,
    ) -> dict:
        """Create a metadata record for a processed file."""
        return {
            "file_name": file_path.name,
            "file_path": str(file_path),
            "file_hash": self.get_file_hash(file_path),
            "clinic_code": clinic_code,
            "tracker_year": tracker_year,
            "tracker_month": tracker_month,
            "last_processed": datetime.now(),
            "processing_time_seconds": processing_time,
            "status": status,
            "patient_count": patient_count,
            "row_count": row_count,
            "error_count": error_count,
            "error_message": error_message,
            "pipeline_version": "2.0.0-python",  # or get from config
            "processed_by": "python-pipeline",
        }

    def update_metadata(self, records: List[dict]):
        """
        Update BigQuery metadata table with new processing records.

        This appends new records (maintaining history).
        """
        if not records:
            logger.info("No metadata records to update")
            return

        df = pl.DataFrame(records)

        # Convert to pandas for BigQuery
        df_pandas = df.to_pandas()

        # Configure load job to append (keep history)
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        # Load to BigQuery
        job = self.client.load_table_from_dataframe(
            df_pandas,
            self.table_id,
            job_config=job_config,
        )

        job.result()  # Wait for completion

        logger.info("Metadata updated", records=len(records), table=self.table_id)

    def get_summary(self) -> dict:
        """Get summary statistics from latest processing run."""
        query = f"""
        WITH latest_run AS (
            SELECT *
            FROM `{self.table_id}`
            WHERE last_processed >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
        )
        SELECT
            COUNT(*) as total_files,
            COUNTIF(status = 'success') as successful,
            COUNTIF(status = 'failed') as failed,
            SUM(patient_count) as total_patients,
            SUM(row_count) as total_rows,
            SUM(error_count) as total_errors,
            SUM(processing_time_seconds) as total_processing_time
        FROM latest_run
        """

        result = self.client.query(query).to_dataframe()

        if len(result) == 0:
            return {}

        return result.iloc[0].to_dict()
```

### Updated Pipeline Script

**scripts/run_pipeline.py** (revised):
```python
#!/usr/bin/env python3
"""
Stateless pipeline for GCP Cloud Run.

Uses BigQuery metadata table for state tracking across runs.
"""

import polars as pl
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import typer
from rich.console import Console
from a4d.config import settings
from a4d.logging import setup_logging, get_logger
from a4d.state.bigquery_state import BigQueryStateManager
from a4d.pipeline.tracker_pipeline import TrackerPipeline
from a4d.gcp.storage import download_bucket, upload_directory
from a4d.tables.create_tables import create_all_tables
from a4d.gcp.bigquery import ingest_all_tables

app = typer.Typer()
console = Console()
logger = get_logger(__name__)


def process_single_tracker(
    tracker_file: Path,
    output_root: Path
) -> tuple[Path, dict, Optional[dict]]:
    """
    Process a single tracker file.

    Returns: (file_path, result, metadata_record)
    """
    pipeline = TrackerPipeline(output_root)
    result = pipeline.process(tracker_file)

    # Extract clinic info from filename or data
    # e.g., "clinic_001_2024_01.xlsx" -> clinic=001, year=2024, month=01
    parts = tracker_file.stem.split("_")
    clinic_code = parts[1] if len(parts) > 1 else None
    tracker_year = int(parts[2]) if len(parts) > 2 else None
    tracker_month = int(parts[3]) if len(parts) > 3 else None

    # Create metadata record
    metadata = None
    if result["success"]:
        metadata = {
            "file_path": tracker_file,
            "clinic_code": clinic_code,
            "tracker_year": tracker_year,
            "tracker_month": tracker_month,
            "status": "success",
            "patient_count": result["patient_count"],
            "row_count": result["row_count"],
            "error_count": result["error_count"],
            "processing_time": result["processing_time"],
            "error_message": None,
        }
    else:
        metadata = {
            "file_path": tracker_file,
            "clinic_code": clinic_code,
            "tracker_year": tracker_year,
            "tracker_month": tracker_month,
            "status": "failed",
            "patient_count": 0,
            "row_count": 0,
            "error_count": 0,
            "processing_time": result["processing_time"],
            "error_message": result.get("error", "Unknown error"),
        }

    return tracker_file, result, metadata


@app.command()
def main(
    max_workers: int = typer.Option(4, help="Number of parallel workers"),
    force: bool = typer.Option(False, help="Force reprocess all files"),
    skip_download: bool = typer.Option(False, help="Skip GCS download"),
    skip_upload: bool = typer.Option(False, help="Skip GCS/BigQuery upload"),
):
    """Run the A4D data processing pipeline (GCP stateless version)."""

    data_dir = settings.data_root
    output_root = settings.output_root

    # Clean output directory (container is fresh each time)
    if output_root.exists():
        import shutil
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    setup_logging(output_root / "logs", "pipeline")

    console.print("\n[bold blue]🚀 A4D Data Pipeline (GCP)[/bold blue]\n")

    # Step 1: Download data from GCS
    if not skip_download:
        console.print("☁️  Downloading data from GCS...")
        download_bucket(settings.download_bucket, data_dir)
        console.print("[green]✅ Download complete[/green]\n")

    # Step 2: Initialize state manager (queries BigQuery)
    console.print("📊 Checking previous processing state...")
    state_manager = BigQueryStateManager(
        project_id=settings.project_id,
        dataset=settings.dataset,
    )

    # Step 3: Discover tracker files
    tracker_files = list(data_dir.rglob("*.xlsx"))
    tracker_files = [f for f in tracker_files if not f.name.startswith("~")]

    console.print(f"📁 Found {len(tracker_files)} tracker files")

    # Step 4: Determine which files need processing (query BigQuery)
    files_to_process = state_manager.get_files_to_process(
        tracker_files,
        force=force
    )

    skipped = len(tracker_files) - len(files_to_process)
    if force:
        console.print(f"⚠️  Force mode: processing all {len(files_to_process)} files")
    else:
        console.print(
            f"✨ Incremental mode: {len(files_to_process)} changed/new, "
            f"{skipped} unchanged (skipped)\n"
        )

    if not files_to_process:
        console.print("[green]✅ No files to process, all up to date![/green]")
        return

    # Step 5: Process trackers in parallel
    console.print(f"🔄 Processing {len(files_to_process)} trackers...\n")

    metadata_records = []
    failed_files = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_single_tracker,
                tracker_file,
                output_root
            ): tracker_file
            for tracker_file in files_to_process
        }

        for future in as_completed(futures):
            tracker_file = futures[future]

            try:
                file_path, result, metadata = future.result()

                if metadata:
                    # Create metadata record for BigQuery
                    metadata_record = state_manager.create_metadata_record(
                        **metadata
                    )
                    metadata_records.append(metadata_record)

                if result["success"]:
                    console.print(
                        f"✅ {file_path.name}: "
                        f"{result['patient_count']} patients, "
                        f"{result['error_count']} errors"
                    )
                else:
                    failed_files.append(file_path)
                    console.print(f"❌ {file_path.name}: FAILED")

            except Exception as e:
                logger.error(
                    "Unexpected error",
                    file=str(tracker_file),
                    error=str(e),
                    exc_info=True,
                )
                failed_files.append(tracker_file)

                # Add failed record
                metadata_record = state_manager.create_metadata_record(
                    file_path=tracker_file,
                    clinic_code=None,
                    tracker_year=None,
                    tracker_month=None,
                    status="failed",
                    error_message=str(e),
                )
                metadata_records.append(metadata_record)

    # Step 6: Create final tables
    console.print("\n[bold]📋 Creating final tables...[/bold]")

    patient_files = list((output_root / "patient_data_cleaned").glob("*.parquet"))
    product_files = list((output_root / "product_data_cleaned").glob("*.parquet"))

    tables_dir = output_root / "tables"
    create_all_tables(patient_files, product_files, tables_dir)

    console.print("[green]✅ Tables created[/green]")

    # Step 7: Upload to GCS and BigQuery
    if not skip_upload:
        console.print("\n[bold]☁️  Uploading to GCS...[/bold]")
        upload_directory(output_root, settings.upload_bucket)

        console.print("[bold]☁️  Uploading to BigQuery...[/bold]")
        ingest_all_tables(tables_dir)

        # Update metadata table in BigQuery
        console.print("[bold]📊 Updating metadata table...[/bold]")
        state_manager.update_metadata(metadata_records)

        console.print("[green]✅ Upload complete[/green]")

    # Print summary
    summary = state_manager.get_summary()
    if summary:
        console.print("\n[bold]📊 Processing Summary[/bold]")
        console.print(f"  ✅ Successful: {summary.get('successful', 0)}")
        console.print(f"  ❌ Failed: {summary.get('failed', 0)}")
        console.print(f"  👥 Total patients: {summary.get('total_patients', 0):,}")
        console.print(f"  📝 Total rows: {summary.get('total_rows', 0):,}")
        console.print(f"  ⚠️  Total errors: {summary.get('total_errors', 0):,}")

    console.print("\n[bold green]🎉 Pipeline complete![/bold green]\n")


if __name__ == "__main__":
    app()
```

## How It Works in GCP

### Cloud Run Flow

```
1. Cloud Scheduler triggers Cloud Run
   ↓
2. Container starts (fresh, no local state)
   ↓
3. Download data from GCS bucket
   ↓
4. Query BigQuery metadata table
   "SELECT file_name, file_hash, status FROM tracker_metadata"
   ↓
5. Compare current file hashes with previous
   ↓
6. Process only changed/new files
   ↓
7. Create final tables
   ↓
8. Upload tables to BigQuery
   ↓
9. Upload metadata table to BigQuery (append new records)
   ↓
10. Container shuts down (state persists in BigQuery)
```

### Next Run

```
1. Container starts fresh again
   ↓
2. Query BigQuery metadata table
   "Oh, I see 153 files were processed yesterday with these hashes"
   ↓
3. Compare with current files
   "Only 3 files changed, I'll process those"
   ↓
4. Process 3 files
   ↓
5. Update metadata table with 3 new records
```

## Advantages

1. ✅ **Stateless**: Works perfectly with Cloud Run
2. ✅ **Persistent**: State survives container restarts
3. ✅ **Incremental**: Only process what changed
4. ✅ **Historical**: Metadata table keeps full history
5. ✅ **Queryable**: Use SQL to analyze processing patterns
6. ✅ **Dashboard-ready**: Same table powers dashboards
7. ✅ **Single source of truth**: One table for state + analytics

## Local Development

For local development, you can use SQLite as a cache (optional):

```python
# Local mode: use SQLite for faster iteration
if settings.environment == "development":
    state_manager = SQLiteStateManager("local_state.db")
else:
    # Production: use BigQuery
    state_manager = BigQueryStateManager(...)
```

But even locally, you can just query BigQuery - it's fast enough.

## Deployment

**Dockerfile** (no changes needed - stateless):
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install uv && uv sync

ENV PYTHONUNBUFFERED=1

CMD ["python", "scripts/run_pipeline.py"]
```

**Deploy**:
```bash
gcloud run deploy a4d-pipeline \
  --source . \
  --memory 4Gi \
  --timeout 3600 \
  --max-instances 1
```

Perfect for your use case! No persistence issues, and you already have the metadata table structure.
