# Per-Tracker Pipeline Architecture

## Philosophy

> Process each tracker file end-to-end, then aggregate. Only reprocess what changed.

## Problems with Current Batch Architecture

**Current R Approach**:
```
Step 1: Process ALL trackers → raw parquets
Step 2: Load ALL raw parquets → clean ALL → cleaned parquets
Step 3: Load ALL cleaned parquets → create tables
```

**Issues**:
1. ❌ Must reprocess everything even if 1 file changed
2. ❌ Memory intensive (load all files at each step)
3. ❌ Long feedback loop (can't see tracker-specific errors until batch completes)
4. ❌ No incremental updates
5. ❌ Difficult to parallelize effectively

## Proposed Per-Tracker Architecture

```
For each tracker file:
  1. Check if changed (hash comparison)
  2. If changed:
     - Extract raw data
     - Clean and validate
     - Export individual cleaned parquet
     - Log errors

After all trackers processed:
  3. Aggregate all cleaned parquets → final tables
  4. Upload to BigQuery
```

**Benefits**:
1. ✅ Only reprocess changed trackers (incremental)
2. ✅ Lower memory footprint (one tracker at a time)
3. ✅ Immediate feedback per tracker
4. ✅ Natural parallelization (process N trackers concurrently)
5. ✅ Failed tracker doesn't block others
6. ✅ Easy to retry individual trackers

## Implementation: No Orchestrator Needed

We can implement this with **simple Python** + **multiprocessing** + **change detection**.

### Change Detection with SQLite

**src/a4d/state/tracker_state.py**:
```python
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class TrackerState:
    """Track state of a processed tracker file."""
    file_path: str
    file_hash: str
    last_processed: datetime
    status: str  # 'success', 'failed', 'processing'
    error_count: int
    row_count: int


class StateManager:
    """Manage processing state for tracker files."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for state tracking."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracker_state (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                last_processed TIMESTAMP NOT NULL,
                status TEXT NOT NULL,
                error_count INTEGER DEFAULT 0,
                row_count INTEGER DEFAULT 0,
                patient_count INTEGER DEFAULT 0,
                processing_time_seconds REAL DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def get_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file."""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            # Read in chunks for large files
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def has_changed(self, file_path: Path) -> bool:
        """Check if file has changed since last processing."""
        current_hash = self.get_file_hash(file_path)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT file_hash, status FROM tracker_state WHERE file_path = ?",
            (str(file_path),)
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            # Never processed
            return True

        stored_hash, status = row

        if status == 'failed':
            # Always reprocess failed files
            return True

        # Changed if hash differs
        return current_hash != stored_hash

    def get_files_to_process(self, tracker_files: List[Path]) -> List[Path]:
        """Get list of files that need processing (new or changed)."""
        return [f for f in tracker_files if self.has_changed(f)]

    def mark_processing(self, file_path: Path):
        """Mark file as currently being processed."""
        file_hash = self.get_file_hash(file_path)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO tracker_state (file_path, file_hash, last_processed, status)
            VALUES (?, ?, ?, 'processing')
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash = excluded.file_hash,
                last_processed = excluded.last_processed,
                status = 'processing'
            """,
            (str(file_path), file_hash, datetime.now())
        )
        conn.commit()
        conn.close()

    def mark_success(
        self,
        file_path: Path,
        error_count: int,
        row_count: int,
        patient_count: int,
        processing_time: float,
    ):
        """Mark file as successfully processed."""
        file_hash = self.get_file_hash(file_path)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO tracker_state
            (file_path, file_hash, last_processed, status, error_count, row_count,
             patient_count, processing_time_seconds)
            VALUES (?, ?, ?, 'success', ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash = excluded.file_hash,
                last_processed = excluded.last_processed,
                status = 'success',
                error_count = excluded.error_count,
                row_count = excluded.row_count,
                patient_count = excluded.patient_count,
                processing_time_seconds = excluded.processing_time_seconds
            """,
            (str(file_path), file_hash, datetime.now(), error_count, row_count,
             patient_count, processing_time)
        )
        conn.commit()
        conn.close()

    def mark_failed(self, file_path: Path, error_message: str):
        """Mark file as failed."""
        file_hash = self.get_file_hash(file_path)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO tracker_state (file_path, file_hash, last_processed, status)
            VALUES (?, ?, ?, 'failed')
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash = excluded.file_hash,
                last_processed = excluded.last_processed,
                status = 'failed'
            """,
            (str(file_path), file_hash, datetime.now())
        )
        conn.commit()
        conn.close()

    def get_summary(self) -> dict:
        """Get summary statistics of all processed files."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT
                COUNT(*) as total_files,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(row_count) as total_rows,
                SUM(patient_count) as total_patients,
                SUM(error_count) as total_errors,
                SUM(processing_time_seconds) as total_processing_time
            FROM tracker_state
        """)
        row = cursor.fetchone()
        conn.close()

        return {
            "total_files": row[0] or 0,
            "successful": row[1] or 0,
            "failed": row[2] or 0,
            "total_rows": row[3] or 0,
            "total_patients": row[4] or 0,
            "total_errors": row[5] or 0,
            "total_processing_time": row[6] or 0,
        }
```

### Per-Tracker Processing Pipeline

**src/a4d/pipeline/tracker_pipeline.py**:
```python
import polars as pl
from pathlib import Path
import time
from a4d.extract.patient import extract_patient_data_from_tracker
from a4d.extract.product import extract_product_data_from_tracker
from a4d.clean.patient import clean_patient_data
from a4d.clean.product import clean_product_data
from a4d.clean.converters import ErrorCollector
from a4d.logging import get_logger

logger = get_logger(__name__)


class TrackerPipeline:
    """Process a single tracker file end-to-end."""

    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.patient_output = output_root / "patient_data_cleaned"
        self.product_output = output_root / "product_data_cleaned"
        self.error_output = output_root / "logs"

        self.patient_output.mkdir(parents=True, exist_ok=True)
        self.product_output.mkdir(parents=True, exist_ok=True)
        self.error_output.mkdir(parents=True, exist_ok=True)

    def process(self, tracker_file: Path) -> dict:
        """
        Process tracker file end-to-end.

        Returns dict with processing stats.
        """
        start_time = time.time()
        error_collector = ErrorCollector()

        logger.info("Processing tracker", file=str(tracker_file))

        try:
            # Step 1: Extract raw data
            patient_df = extract_patient_data_from_tracker(tracker_file)
            product_df = extract_product_data_from_tracker(tracker_file)

            if patient_df is None or len(patient_df) == 0:
                logger.warning("No patient data extracted", file=str(tracker_file))
                patient_count = 0
                row_count = 0
            else:
                # Step 2: Clean patient data
                patient_df_cleaned = clean_patient_data(
                    patient_df,
                    error_collector
                )

                # Step 3: Export cleaned data
                patient_output_file = (
                    self.patient_output /
                    f"{tracker_file.stem}_patient_cleaned.parquet"
                )
                patient_df_cleaned.write_parquet(
                    patient_output_file,
                    compression="zstd"
                )

                patient_count = patient_df_cleaned["patient_id"].n_unique()
                row_count = len(patient_df_cleaned)

            # Same for product data
            if product_df is not None and len(product_df) > 0:
                product_df_cleaned = clean_product_data(
                    product_df,
                    error_collector
                )

                product_output_file = (
                    self.product_output /
                    f"{tracker_file.stem}_product_cleaned.parquet"
                )
                product_df_cleaned.write_parquet(
                    product_output_file,
                    compression="zstd"
                )

            # Export error log
            if error_collector.errors:
                error_df = error_collector.to_dataframe()
                error_file = self.error_output / f"{tracker_file.stem}_errors.parquet"
                error_df.write_parquet(error_file)

            processing_time = time.time() - start_time

            logger.info(
                "Tracker processed successfully",
                file=str(tracker_file),
                patient_count=patient_count,
                row_count=row_count,
                error_count=len(error_collector.errors),
                processing_time=f"{processing_time:.2f}s",
            )

            return {
                "success": True,
                "patient_count": patient_count,
                "row_count": row_count,
                "error_count": len(error_collector.errors),
                "processing_time": processing_time,
            }

        except Exception as e:
            logger.error(
                "Tracker processing failed",
                file=str(tracker_file),
                error=str(e),
                exc_info=True,
            )
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time,
            }
```

### Main Pipeline with Parallel Processing

**scripts/run_pipeline.py**:
```python
#!/usr/bin/env python3
"""
Main pipeline: Process trackers incrementally with parallel execution.

Architecture:
1. Discover all tracker files
2. Check which ones changed (hash comparison)
3. Process changed trackers in parallel (end-to-end per tracker)
4. Aggregate all cleaned parquets → final tables
5. Upload to BigQuery
"""

import polars as pl
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.console import Console
from a4d.config import settings
from a4d.logging import setup_logging, get_logger
from a4d.state.tracker_state import StateManager
from a4d.pipeline.tracker_pipeline import TrackerPipeline
from a4d.tables.create_tables import create_all_tables
from a4d.gcp.bigquery import ingest_all_tables

app = typer.Typer()
console = Console()
logger = get_logger(__name__)


def process_single_tracker(tracker_file: Path, output_root: Path) -> tuple[Path, dict]:
    """
    Process a single tracker file (for parallel execution).

    Returns: (tracker_file, result_dict)
    """
    pipeline = TrackerPipeline(output_root)
    result = pipeline.process(tracker_file)
    return tracker_file, result


@app.command()
def main(
    max_workers: int = typer.Option(4, help="Number of parallel workers"),
    force: bool = typer.Option(False, help="Force reprocess all files"),
    skip_bigquery: bool = typer.Option(False, help="Skip BigQuery upload"),
):
    """Run the A4D data processing pipeline."""

    output_root = settings.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    setup_logging(output_root / "logs", "pipeline")

    console.print("\n[bold blue]🚀 A4D Data Pipeline[/bold blue]\n")

    # Initialize state manager
    state_db = output_root / "state" / "tracker_state.db"
    state_manager = StateManager(state_db)

    # Discover tracker files
    tracker_files = list(settings.tracker_root.rglob("*.xlsx"))
    tracker_files = [f for f in tracker_files if not f.name.startswith("~")]

    console.print(f"📁 Found {len(tracker_files)} tracker files")

    # Determine which files need processing
    if force:
        files_to_process = tracker_files
        console.print(f"⚠️  Force mode: processing all {len(files_to_process)} files")
    else:
        files_to_process = state_manager.get_files_to_process(tracker_files)
        skipped = len(tracker_files) - len(files_to_process)
        console.print(
            f"✨ Incremental mode: {len(files_to_process)} changed/new, "
            f"{skipped} unchanged (skipped)"
        )

    if not files_to_process:
        console.print("[green]✅ No files to process, all up to date![/green]")
        return

    # Process trackers in parallel
    console.print(f"\n🔄 Processing {len(files_to_process)} trackers "
                  f"({max_workers} workers)...\n")

    results = {}
    failed_files = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Processing trackers...",
            total=len(files_to_process)
        )

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs
            futures = {
                executor.submit(
                    process_single_tracker,
                    tracker_file,
                    output_root
                ): tracker_file
                for tracker_file in files_to_process
            }

            # Process results as they complete
            for future in as_completed(futures):
                tracker_file = futures[future]

                try:
                    file_path, result = future.result()
                    results[file_path] = result

                    if result["success"]:
                        # Update state
                        state_manager.mark_success(
                            file_path,
                            error_count=result["error_count"],
                            row_count=result["row_count"],
                            patient_count=result["patient_count"],
                            processing_time=result["processing_time"],
                        )

                        console.print(
                            f"✅ {file_path.name}: "
                            f"{result['patient_count']} patients, "
                            f"{result['error_count']} errors, "
                            f"{result['processing_time']:.1f}s"
                        )
                    else:
                        state_manager.mark_failed(file_path, result.get("error", "Unknown"))
                        failed_files.append(file_path)
                        console.print(f"❌ {file_path.name}: FAILED - {result.get('error')}")

                except Exception as e:
                    logger.error(
                        "Unexpected error processing tracker",
                        file=str(tracker_file),
                        error=str(e),
                        exc_info=True,
                    )
                    state_manager.mark_failed(tracker_file, str(e))
                    failed_files.append(tracker_file)
                    console.print(f"❌ {tracker_file.name}: FAILED - {e}")

                progress.advance(task)

    # Print summary
    console.print("\n[bold]📊 Processing Summary[/bold]")
    summary = state_manager.get_summary()
    console.print(f"  Total files in DB: {summary['total_files']}")
    console.print(f"  ✅ Successful: {summary['successful']}")
    console.print(f"  ❌ Failed: {summary['failed']}")
    console.print(f"  👥 Total patients: {summary['total_patients']:,}")
    console.print(f"  📝 Total rows: {summary['total_rows']:,}")
    console.print(f"  ⚠️  Total errors: {summary['total_errors']:,}")
    console.print(f"  ⏱️  Total processing time: {summary['total_processing_time']:.1f}s")

    if failed_files:
        console.print(f"\n[red]❌ {len(failed_files)} files failed - check logs[/red]")
        logger.warning("Failed files", files=[str(f) for f in failed_files])

    # Step 2: Create final tables from all cleaned parquets
    console.print("\n[bold]📋 Creating final tables...[/bold]")

    patient_files = list((output_root / "patient_data_cleaned").glob("*.parquet"))
    product_files = list((output_root / "product_data_cleaned").glob("*.parquet"))

    console.print(f"  📄 {len(patient_files)} patient parquet files")
    console.print(f"  📄 {len(product_files)} product parquet files")

    tables_dir = output_root / "tables"
    create_all_tables(patient_files, product_files, tables_dir)

    console.print("[green]✅ Tables created[/green]")

    # Step 3: Upload to BigQuery
    if not skip_bigquery:
        console.print("\n[bold]☁️  Uploading to BigQuery...[/bold]")
        ingest_all_tables(tables_dir)
        console.print("[green]✅ Upload complete[/green]")
    else:
        console.print("\n⏭️  Skipping BigQuery upload")

    console.print("\n[bold green]🎉 Pipeline complete![/bold green]\n")


@app.command()
def status():
    """Show pipeline status and statistics."""
    state_db = settings.output_root / "state" / "tracker_state.db"
    state_manager = StateManager(state_db)

    summary = state_manager.get_summary()

    console.print("\n[bold]📊 Pipeline Status[/bold]\n")
    console.print(f"Total files tracked: {summary['total_files']}")
    console.print(f"✅ Successful: {summary['successful']}")
    console.print(f"❌ Failed: {summary['failed']}")
    console.print(f"👥 Total patients: {summary['total_patients']:,}")
    console.print(f"📝 Total rows: {summary['total_rows']:,}")
    console.print(f"⚠️  Total errors: {summary['total_errors']:,}")
    console.print(f"⏱️  Total processing time: {summary['total_processing_time']:.1f}s\n")


@app.command()
def reset():
    """Reset state database (force full reprocessing on next run)."""
    state_db = settings.output_root / "state" / "tracker_state.db"

    if state_db.exists():
        state_db.unlink()
        console.print("[green]✅ State reset - next run will reprocess all files[/green]")
    else:
        console.print("[yellow]ℹ️  No state database found[/yellow]")


if __name__ == "__main__":
    app()
```

## Usage

```bash
# First run: processes all trackers
python scripts/run_pipeline.py

# Subsequent runs: only changed trackers
python scripts/run_pipeline.py

# Check status
python scripts/run_pipeline.py status

# Force reprocess all
python scripts/run_pipeline.py --force

# Use 8 workers for parallel processing
python scripts/run_pipeline.py --max-workers 8

# Skip BigQuery upload (testing)
python scripts/run_pipeline.py --skip-bigquery

# Reset state (force full reprocess next time)
python scripts/run_pipeline.py reset
```

## Output Example

```
🚀 A4D Data Pipeline

📁 Found 156 tracker files
✨ Incremental mode: 3 changed/new, 153 unchanged (skipped)

🔄 Processing 3 trackers (4 workers)...

✅ clinic_001_2024_01.xlsx: 45 patients, 2 errors, 1.2s
✅ clinic_003_2024_02.xlsx: 38 patients, 0 errors, 0.9s
✅ clinic_012_2024_01.xlsx: 52 patients, 1 errors, 1.4s

📊 Processing Summary
  Total files in DB: 156
  ✅ Successful: 156
  ❌ Failed: 0
  👥 Total patients: 7,234
  📝 Total rows: 45,678
  ⚠️  Total errors: 234
  ⏱️  Total processing time: 189.3s

📋 Creating final tables...
  📄 156 patient parquet files
  📄 156 product parquet files
✅ Tables created

☁️  Uploading to BigQuery...
✅ Upload complete

🎉 Pipeline complete!
```

## Advantages

1. **Incremental**: Only reprocess what changed (hash-based detection)
2. **Fast**: Parallel processing of independent trackers
3. **Resilient**: One failed tracker doesn't block others
4. **Transparent**: See results per tracker immediately
5. **Stateful**: Tracks what's been processed (SQLite)
6. **Simple**: No orchestrator framework needed
7. **Memory efficient**: One tracker at a time
8. **Easy to retry**: Failed trackers automatically retried on next run

## Why No Orchestrator?

**Prefect/doit/Airflow add**:
- Complex dependency DAG management
- Scheduling infrastructure
- UI dashboards
- Distributed execution

**We don't need**:
- ❌ Complex DAG (simple: trackers → tables → BigQuery)
- ❌ Scheduling (GCP Cloud Scheduler handles that)
- ❌ Distributed execution (multiprocessing is sufficient)
- ❌ Extra infrastructure (SQLite + Python is enough)

**We get instead**:
- ✅ Simple Python code
- ✅ Easy to understand and debug
- ✅ Fast local testing
- ✅ No framework lock-in
- ✅ Easy deployment (just Python + Docker)

## GCP Deployment

**Option 1: Cloud Run (Recommended)**
```dockerfile
# Same Dockerfile as before
# Deploy: gcloud run deploy a4d-pipeline --source .
# Trigger: Cloud Scheduler → Cloud Run
```

**Option 2: Cloud Functions (Event-driven)**
```python
# Trigger on new file uploaded to GCS
# Process only that file
# Good for real-time processing
```

**Option 3: Compute Engine VM**
```bash
# Cron job: 0 2 * * * cd /app && python scripts/run_pipeline.py
# Good for batch processing
```

## Conclusion

✅ **Per-tracker architecture is better**
✅ **Incremental processing is essential**
✅ **No orchestrator needed** - simple Python + multiprocessing
✅ **State management with SQLite** - lightweight and effective
✅ **Easy to understand, deploy, and maintain**

This gives you the benefits of modern orchestration (incremental, parallel, stateful) without the complexity.
