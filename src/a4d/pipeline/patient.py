"""Main patient pipeline orchestration."""

import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from a4d.config import settings
from a4d.logging import setup_logging
from a4d.pipeline.models import PipelineResult, TrackerResult
from a4d.pipeline.tracker import process_tracker_patient
from a4d.tables.errors import create_table_errors
from a4d.tables.logs import create_table_logs
from a4d.tables.patient import (
    create_table_patient_data_annual,
    create_table_patient_data_monthly,
    create_table_patient_data_static,
)


def _init_worker_logging(output_root: Path) -> None:
    """Initialize logging for worker processes (called once per ProcessPoolExecutor worker)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid = os.getpid()
    setup_logging(
        output_root=output_root,
        log_name=f"worker_{timestamp}_pid{pid}",
        console_level="ERROR",
    )


def discover_tracker_files(data_root: Path) -> list[Path]:
    """Discover all Excel tracker files in data_root.

    Searches recursively for .xlsx files, excluding temp files (~$*).

    Args:
        data_root: Root directory to search

    Returns:
        List of tracker file paths

    Example:
        >>> tracker_files = discover_tracker_files(Path("/data"))
        >>> len(tracker_files)
        42
    """
    tracker_files = []
    for file in data_root.rglob("*.xlsx"):
        if not file.name.startswith("~$"):
            tracker_files.append(file)

    return sorted(tracker_files)


def process_patient_tables(cleaned_dir: Path, output_dir: Path) -> dict[str, Path]:
    """Create final patient tables from cleaned parquets.

    Creates three main tables:
    - patient_data_static: Latest data per patient
    - patient_data_monthly: All monthly records
    - patient_data_annual: Latest data per patient per year (2024+)

    Args:
        cleaned_dir: Directory containing cleaned parquet files
        output_dir: Directory to write final tables

    Returns:
        Dictionary mapping table name to output path

    Example:
        >>> tables = process_patient_tables(
        ...     Path("output/patient_data_cleaned"),
        ...     Path("output/tables")
        ... )
        >>> tables.keys()
        dict_keys(['static', 'monthly', 'annual'])
    """
    logger.info("Creating final patient tables from cleaned data")

    cleaned_files = list(cleaned_dir.glob("*_patient_cleaned.parquet"))
    logger.info(f"Found {len(cleaned_files)} cleaned parquet files")

    if not cleaned_files:
        logger.warning("No cleaned files found, skipping table creation")
        return {}

    tables = {}

    logger.info("Creating static patient table")
    static_path = create_table_patient_data_static(cleaned_files, output_dir)
    tables["static"] = static_path

    logger.info("Creating monthly patient table")
    monthly_path = create_table_patient_data_monthly(cleaned_files, output_dir)
    tables["monthly"] = monthly_path

    logger.info("Creating annual patient table")
    annual_path = create_table_patient_data_annual(cleaned_files, output_dir)
    tables["annual"] = annual_path

    logger.info(f"Created {len(tables)} patient tables")
    return tables


def run_patient_pipeline(
    tracker_files: list[Path] | None = None,
    max_workers: int = 1,
    output_root: Path | None = None,
    skip_tables: bool = False,
    force: bool = False,
    clean_output: bool = False,
    progress_callback: Callable[[str, bool], None] | None = None,
    show_progress: bool = False,
    console_log_level: str | None = None,
) -> PipelineResult:
    """Run complete patient data pipeline.

    Processing modes:
    - Batch mode: If tracker_files is None, discovers all .xlsx in data_root
    - Single file mode: If tracker_files provided, processes only those files

    Pipeline steps:
    1. For each tracker (optionally parallel):
        - Extract patient data from Excel → raw parquet
        - Clean raw data → cleaned parquet
    2. Create final tables from all cleaned parquets (if not skipped)

    Args:
        tracker_files: Specific files to process (None = discover all)
        max_workers: Number of parallel workers (1 = sequential)
        output_root: Output directory (None = use settings.output_root)
        skip_tables: If True, only extract + clean, skip table creation
        force: If True, reprocess even if outputs exist
        clean_output: If True, wipe patient_data_raw/, patient_data_cleaned/, tables/ before run
        progress_callback: Optional callback(tracker_name, success) called after each tracker
        show_progress: If True, show tqdm progress bar
        console_log_level: Console log level (None=INFO, ERROR=quiet, etc)

    Returns:
        PipelineResult with tracker results and table paths

    Example:
        >>> # Process all trackers
        >>> result = run_patient_pipeline()
        >>> result.success
        True
        >>> result.successful_trackers
        42

        >>> # Process single file
        >>> result = run_patient_pipeline(
        ...     tracker_files=[Path("/data/2024_Sibu.xlsx")]
        ... )

        >>> # Parallel processing with progress bar (CLI mode)
        >>> result = run_patient_pipeline(
        ...     max_workers=8,
        ...     show_progress=True,
        ...     console_log_level="ERROR"
        ... )
    """
    import shutil

    # Use settings defaults if not provided
    if output_root is None:
        output_root = settings.output_root

    # Wipe previous run's outputs so tables reflect only this run.
    if clean_output:
        for subdir in ("patient_data_raw", "patient_data_cleaned", "tables", "logs"):
            target = output_root / subdir
            if target.exists():
                shutil.rmtree(target)
                logger.info(f"Cleaned output directory: {target}")

    # Setup main pipeline logging
    setup_logging(
        output_root,
        "pipeline_patient",
        console_level=console_log_level if console_log_level else "INFO",
    )
    logger.info("Starting patient pipeline")
    logger.info(f"Output directory: {output_root}")
    logger.info(f"Max workers: {max_workers}")

    # Discover or use provided tracker files
    if tracker_files is None:
        logger.info(f"Discovering tracker files in: {settings.data_root}")
        tracker_files = discover_tracker_files(settings.data_root)
    else:
        tracker_files = [Path(f) for f in tracker_files]

    logger.info(f"Found {len(tracker_files)} tracker files to process")

    if not tracker_files:
        logger.warning("No tracker files found")
        return PipelineResult.from_tracker_results([], {})

    # Process trackers
    tracker_results: list[TrackerResult] = []

    if max_workers == 1:
        # Sequential processing (easier for debugging)
        logger.info("Processing trackers sequentially")

        # Use tqdm if requested
        iterator = (
            tqdm(tracker_files, desc="Processing trackers", unit="file")
            if show_progress
            else tracker_files
        )

        for tracker_file in iterator:
            if isinstance(iterator, tqdm):
                iterator.set_description(f"Processing {tracker_file.name}")

            result = process_tracker_patient(
                tracker_file=tracker_file,
                output_root=output_root,
                mapper=None,  # Each tracker loads mapper if needed
            )
            tracker_results.append(result)

            # Call progress callback if provided
            if progress_callback:
                progress_callback(tracker_file.name, result.success)

            if result.success:
                logger.info(f"✓ Successfully processed: {tracker_file.name}")
                if show_progress:
                    tqdm.write(f"✓ {tracker_file.name}")
            else:
                logger.error(f"✗ Failed to process: {tracker_file.name} - {result.error}")
                if show_progress:
                    tqdm.write(f"✗ {tracker_file.name}: {result.error}")

    else:
        # Parallel processing
        logger.info(f"Processing trackers in parallel ({max_workers} workers)")
        with ProcessPoolExecutor(
            max_workers=max_workers, initializer=_init_worker_logging, initargs=(output_root,)
        ) as executor:
            # Submit all jobs
            futures = {
                executor.submit(
                    process_tracker_patient,
                    tracker_file,
                    output_root,
                    None,  # Each worker loads synonyms independently
                ): tracker_file
                for tracker_file in tracker_files
            }

            # Collect results as they complete
            futures_iterator = as_completed(futures)
            if show_progress:
                futures_iterator = tqdm(
                    futures_iterator, total=len(futures), desc="Processing trackers", unit="file"
                )

            for future in futures_iterator:
                tracker_file = futures[future]
                try:
                    result = future.result()
                    tracker_results.append(result)

                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback(tracker_file.name, result.success)

                    if result.success:
                        logger.info(f"✓ Completed: {tracker_file.name}")
                        if show_progress:
                            tqdm.write(f"✓ {tracker_file.name}")
                    else:
                        logger.error(f"✗ Failed: {tracker_file.name} - {result.error}")
                        if show_progress:
                            tqdm.write(f"✗ {tracker_file.name}: {result.error}")
                except Exception as e:
                    logger.exception(f"Exception processing {tracker_file.name}")
                    if show_progress:
                        tqdm.write(f"✗ {tracker_file.name}: Exception - {str(e)}")
                    tracker_results.append(
                        TrackerResult(
                            tracker_file=tracker_file,
                            tracker_name=tracker_file.stem,
                            success=False,
                            error=str(e),
                        )
                    )

    # Summary
    successful = sum(1 for r in tracker_results if r.success)
    failed = len(tracker_results) - successful
    logger.info(f"Tracker processing complete: {successful} successful, {failed} failed")

    # Create tables
    tables: dict[str, Path] = {}
    if not skip_tables:
        try:
            cleaned_dir = output_root / "patient_data_cleaned"
            tables_dir = output_root / "tables"
            logs_dir = output_root / "logs"

            tables = process_patient_tables(cleaned_dir, tables_dir)

            # Create logs table separately (operational data, not patient data)
            if logs_dir.exists():
                logger.info("Creating logs table from pipeline execution logs")
                logs_table_path = create_table_logs(logs_dir, tables_dir)
                tables["logs"] = logs_table_path
                logger.info(f"Logs table created: {logs_table_path}")

            # Aggregate all data quality errors from every tracker into one table
            all_data_errors = [e for r in tracker_results for e in r.data_errors]
            logger.info(f"Creating errors table ({len(all_data_errors)} total data quality errors)")
            errors_table_path = create_table_errors(all_data_errors, tables_dir)
            tables["errors"] = errors_table_path
            logger.info(f"Errors table created: {errors_table_path}")

            logger.info(f"Created {len(tables)} tables total")
        except Exception:
            logger.exception("Failed to create tables")
            # Don't fail entire pipeline if table creation fails
    else:
        logger.info("Skipping table creation (skip_tables=True)")

    # Build result
    result = PipelineResult.from_tracker_results(tracker_results, tables)

    if result.success:
        logger.info("✓ Pipeline completed successfully")
    else:
        logger.warning(f"✗ Pipeline completed with {failed} failures")

    return result
