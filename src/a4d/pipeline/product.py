"""Product pipeline orchestration.

Mirrors ``pipeline/patient.py``: per-tracker extract+clean (optionally
parallel), followed by final-table creation.
"""

import os
import shutil
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from a4d.config import settings
from a4d.findings import Finding
from a4d.logging import setup_logging
from a4d.pipeline.models import PipelineResult, TrackerResult
from a4d.pipeline.patient import discover_tracker_files
from a4d.pipeline.tracker import process_tracker_product
from a4d.tables.product import create_table_product_data


def _init_worker_logging(output_root: Path) -> None:
    """Initialize logging for worker processes (called once per ProcessPoolExecutor worker)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid = os.getpid()
    setup_logging(
        output_root=output_root,
        log_name=f"worker_product_{timestamp}_pid{pid}",
        console_level="ERROR",
    )


def process_product_tables(
    cleaned_dir: Path, output_dir: Path
) -> tuple[dict[str, Path], list[Finding]]:
    """Create the final product table from cleaned parquets.

    Thin wrapper around ``tables.product.create_table_product_data``.
    Unlike the patient pipeline (static/monthly/annual) the product pipeline
    emits a single ``product_data`` table.

    Returns:
        The tables created, and the findings the table stage emitted -- the
        stage runs outside any tracker's context, so its findings reach the
        run's findings table only by being handed back.
    """
    logger.info("Creating final product table from cleaned data")

    cleaned_files = list(cleaned_dir.glob("*_product_cleaned.parquet"))
    logger.info(f"Found {len(cleaned_files)} cleaned product parquet files")

    if not cleaned_files:
        logger.warning("No cleaned product files found, skipping table creation")
        return {}, []

    product_data_path, findings = create_table_product_data(cleaned_files, output_dir)
    return {"product_data": product_data_path}, findings


def run_product_pipeline(
    tracker_files: list[Path] | None = None,
    max_workers: int = 1,
    output_root: Path | None = None,
    skip_tables: bool = False,
    clean_output: bool = False,
    progress_callback: Callable[[str, bool], None] | None = None,
    show_progress: bool = False,
    console_log_level: str | None = None,
) -> PipelineResult:
    """Run the end-to-end product pipeline.

    Mirrors ``run_patient_pipeline`` argument-for-argument.
    """
    if output_root is None:
        output_root = settings.output_root

    if clean_output:
        for subdir in ("product_data_raw", "product_data_cleaned"):
            target = output_root / subdir
            if target.exists():
                shutil.rmtree(target)
                logger.info(f"Cleaned output directory: {target}")
        # Patient tables share output_root/tables; remove only the product table.
        product_table = output_root / "tables" / "product_data.parquet"
        if product_table.exists():
            product_table.unlink()
            logger.info(f"Cleaned product table: {product_table}")

    setup_logging(
        output_root,
        "pipeline_product",
        console_level=console_log_level if console_log_level else "INFO",
    )
    logger.info("Starting product pipeline")
    logger.info(f"Output directory: {output_root}")
    logger.info(f"Max workers: {max_workers}")

    if tracker_files is None:
        logger.info(f"Discovering tracker files in: {settings.data_root}")
        tracker_files = discover_tracker_files(settings.data_root)
    else:
        tracker_files = [Path(f) for f in tracker_files]

    logger.info(f"Found {len(tracker_files)} tracker files to process")

    if not tracker_files:
        logger.warning("No tracker files found")
        return PipelineResult.from_tracker_results([], {})

    tracker_results: list[TrackerResult] = []

    if max_workers == 1:
        logger.info("Processing trackers sequentially")

        iterator = (
            tqdm(tracker_files, desc="Processing product trackers", unit="file")
            if show_progress
            else tracker_files
        )

        for tracker_file in iterator:
            if isinstance(iterator, tqdm):
                iterator.set_description(f"Processing {tracker_file.name}")

            result = process_tracker_product(
                tracker_file=tracker_file,
                output_root=output_root,
                mapper=None,
            )
            tracker_results.append(result)

            if progress_callback:
                progress_callback(tracker_file.name, result.success)

            if result.success:
                logger.info(f"✓ Successfully processed: {tracker_file.name}")
            else:
                logger.error(f"✗ Failed to process: {tracker_file.name} - {result.error}")
                if show_progress:
                    tqdm.write(f"✗ {tracker_file.name}: {result.error}")

    else:
        logger.info(f"Processing trackers in parallel ({max_workers} workers)")
        with ProcessPoolExecutor(
            max_workers=max_workers, initializer=_init_worker_logging, initargs=(output_root,)
        ) as executor:
            futures = {
                executor.submit(
                    process_tracker_product,
                    tracker_file,
                    output_root,
                    None,
                ): tracker_file
                for tracker_file in tracker_files
            }

            futures_iterator = as_completed(futures)
            if show_progress:
                futures_iterator = tqdm(
                    futures_iterator,
                    total=len(futures),
                    desc="Processing product trackers",
                    unit="file",
                )

            for future in futures_iterator:
                tracker_file = futures[future]
                try:
                    result = future.result()
                    tracker_results.append(result)

                    if progress_callback:
                        progress_callback(tracker_file.name, result.success)

                    if result.success:
                        logger.info(f"✓ Completed: {tracker_file.name}")
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

    successful = sum(1 for r in tracker_results if r.success)
    failed = len(tracker_results) - successful
    logger.info(f"Tracker processing complete: {successful} successful, {failed} failed")

    tables: dict[str, Path] = {}
    table_findings: list[Finding] = []
    if not skip_tables:
        try:
            cleaned_dir = output_root / "product_data_cleaned"
            tables_dir = output_root / "tables"
            tables, table_findings = process_product_tables(cleaned_dir, tables_dir)
            logger.info(f"Created {len(tables)} product tables total")
        except Exception:
            logger.exception("Failed to create product tables")
    else:
        logger.info("Skipping product table creation (skip_tables=True)")

    result = PipelineResult.from_tracker_results(tracker_results, tables, table_findings)

    if result.success:
        logger.info("✓ Product pipeline completed successfully")
    else:
        logger.warning(f"✗ Product pipeline completed with {failed} failures")

    return result
