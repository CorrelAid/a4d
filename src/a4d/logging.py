"""Operational logging configuration using loguru.

This module provides logging infrastructure for monitoring and debugging
the pipeline execution. Logs are exported to BigQuery for dashboard analysis
(success rates, error counts, processing times, etc.).

For data quality errors (conversion failures, validation errors),
use report_finding from a4d.findings instead.

Usage:
    The loguru logger is a singleton. Once configured with setup_logging(),
    all imports of 'from loguru import logger' will use the same configuration.

    >>> from a4d.logging import setup_logging, file_logger
    >>> setup_logging(output_root=Path("output"), log_name="main_pipeline")
    >>>
    >>> # In processing code:
    >>> from loguru import logger
    >>> with file_logger("clinic_001_patient", output_root, tracker_year=2024, tracker_month=10):
    ...     logger.info("Processing started", rows=150)
    ...     logger.warning("Missing column", column="hba1c_updated_date")
"""

import shutil
import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from loguru import logger


def clear_run_logs(output_root: Path, *, keep_per_tracker: bool = False) -> None:
    """Drop the previous run's log files before this run opens its own sinks.

    Both readers of ``output_root/logs/`` -- :func:`a4d.tables.logs.create_table_logs`
    and :func:`a4d.tables.findings.rebuild_findings_from_logs` -- take every
    ``*.log`` file in the directory. Per-tracker logs are safe on their own,
    since :func:`file_logger` deletes and rewrites each one by name. The
    aggregate logs are not: ``main_worker_<timestamp>_pid<n>.log`` is a fresh
    name every run and loguru's file sink appends rather than truncates, so a
    second run in the same directory left both readers summing two runs. It
    returned 213,921 findings for a run that produced 105,464.

    Args:
        output_root: Root output directory (logs live in ``output_root/logs/``)
        keep_per_tracker: Keep the per-tracker logs and drop only the aggregate
            ``main_*`` ones. Set under ``--incremental``, where a tracker the
            run skips has no other record of its findings -- its lines in the
            previous run's worker log are duplicates of its own log file, never
            the only copy.
    """
    log_dir = output_root / "logs"
    if not log_dir.exists():
        return

    if not keep_per_tracker:
        shutil.rmtree(log_dir)
        return

    # Aggregate logs are the ones setup_logging names, which prefixes "main_".
    # Rotation writes siblings (.zip) under the same prefix, so match on it
    # rather than on the .log suffix.
    for stale in log_dir.glob("main_*"):
        stale.unlink()


def _main_thread_only(record) -> bool:  # noqa: ANN001
    """Filter that passes only log records from the main thread.

    Used on the console handler when running parallel workers so that
    worker thread logs don't flood the console or break tqdm progress bars.
    Worker logs still reach their per-tracker JSON file handlers.
    """
    return threading.current_thread() is threading.main_thread()


def setup_logging(
    output_root: Path,
    log_name: str,
    level: str = "INFO",
    console: bool = True,
    console_level: str | None = None,
    console_main_thread_only: bool = False,
) -> None:
    """Configure loguru for pipeline-wide operational logging.

    Creates both console (colored, human-readable) and file (JSON for BigQuery)
    handlers. All logs in the JSON file include context variables from
    contextualize() for analysis in Looker Studio.

    Args:
        output_root: Root output directory (logs will be in output_root/logs/)
        log_name: Base name for the log file (e.g., "script1_extract")
        level: Minimum file log level (DEBUG, INFO, WARNING, ERROR)
        console: Whether to add console handler (set False for CLI with progress bars)
        console_level: Console log level (None = use level, or set to ERROR for quiet mode)

    Example:
        >>> setup_logging(Path("output"), "script1_extract")
        >>> logger.info("Processing started", total_trackers=10)

        >>> # Quiet mode for CLI with progress bars
        >>> setup_logging(Path("output"), "pipeline", console_level="ERROR")
    """
    log_dir = output_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"main_{log_name}.log"

    # Remove default handler
    logger.remove()

    # Console handler: pretty, colored output for monitoring
    if console:
        console_log_level = console_level if console_level is not None else level
        logger.add(
            sys.stdout,
            level=console_log_level,
            colorize=True,
            filter=_main_thread_only if console_main_thread_only else None,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<level>{message}</level>"
            ),
        )

    # File handler: JSON output for BigQuery upload
    # serialize=True means all context from contextualize() is included
    logger.add(
        log_file,
        level="DEBUG",  # Capture all levels in file
        serialize=True,  # JSON format with all fields
        rotation="100 MB",
        retention="30 days",
        compression="zip",
    )

    if console:
        logger.info("Logging initialized", log_file=str(log_file), level=level)


@contextmanager
def file_logger(
    file_name: str,
    output_root: Path,
    tracker_year: int | None = None,
    tracker_month: int | None = None,
    level: str = "DEBUG",
) -> Generator:
    """Context manager for per-tracker file logging with context.

    Creates a separate log file for a specific tracker and sets context
    variables (file_name, tracker_year, tracker_month) that are automatically
    included in all log records within this context.

    All logs are JSON formatted and will be aggregated for BigQuery upload.

    Args:
        file_name: Name of the tracker file (e.g., "clinic_001_patient")
        output_root: Root output directory (logs will be in output_root/logs/)
        tracker_year: Year from the tracker (for dashboard filtering)
        tracker_month: Month from the tracker (for dashboard filtering)
        level: Minimum log level for this file handler

    Yields:
        None (use logger directly within context)

    Example:
        >>> with file_logger("clinic_001_patient", output_root, 2024, 10):
        ...     logger.info("Processing patient data", rows=150)
        ...     logger.warning("Missing column", column="hba1c_updated_date")
        ...     # All logs include file_name, tracker_year, tracker_month
    """
    log_dir = output_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{file_name}.log"

    # Remove old log file if exists
    if log_file.exists():
        log_file.unlink()

    # Add file-specific handler (JSON only, no console)
    handler_id = logger.add(
        log_file,
        level=level,
        serialize=True,  # JSON format
    )

    # Build context dict (only include non-None values)
    context = {"file_name": file_name}
    if tracker_year is not None:
        context["tracker_year"] = tracker_year
    if tracker_month is not None:
        context["tracker_month"] = tracker_month

    # Use contextualize to add file_name, tracker_year, tracker_month to all logs
    with logger.contextualize(**context):
        try:
            yield
        except Exception:
            # Log exception with full traceback
            logger.bind(error_code="critical_abort").exception("Processing failed")
            raise
        finally:
            # Remove the handler
            logger.remove(handler_id)
