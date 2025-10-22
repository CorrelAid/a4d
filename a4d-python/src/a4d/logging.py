"""Operational logging configuration using loguru.

This module provides logging infrastructure for monitoring and debugging
the pipeline execution. Logs are exported to BigQuery for dashboard analysis
(success rates, error counts, processing times, etc.).

For data quality errors (conversion failures, validation errors),
use the ErrorCollector class from a4d.errors instead.

Usage:
    The loguru logger is a singleton. Once configured with setup_logging(),
    all imports of 'from loguru import logger' will use the same configuration.

    >>> from a4d.logging import setup_logging, file_logger
    >>> setup_logging(output_root=Path("output"), log_name="script1")
    >>>
    >>> # In processing code:
    >>> from loguru import logger
    >>> with file_logger("clinic_001_patient", output_root, tracker_year=2024, tracker_month=10):
    ...     logger.info("Processing started", rows=150)
    ...     logger.warning("Missing column", column="hba1c_updated_date")
"""

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from loguru import logger


def setup_logging(output_root: Path, log_name: str, level: str = "INFO") -> None:
    """Configure loguru for pipeline-wide operational logging.

    Creates both console (colored, human-readable) and file (JSON for BigQuery)
    handlers. All logs in the JSON file include context variables from
    contextualize() for analysis in Looker Studio.

    Args:
        output_root: Root output directory (logs will be in output_root/logs/)
        log_name: Base name for the log file (e.g., "script1_extract")
        level: Minimum console log level (DEBUG, INFO, WARNING, ERROR)

    Example:
        >>> setup_logging(Path("output"), "script1_extract")
        >>> logger.info("Processing started", total_trackers=10)
    """
    log_dir = output_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"main_{log_name}.log"

    # Remove default handler
    logger.remove()

    # Console handler: pretty, colored output for monitoring
    # Include some context in format for readability
    logger.add(
        sys.stdout,
        level=level,
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
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

    logger.info("Logging initialized", log_file=str(log_file), level=level)


@contextmanager
def file_logger(
    file_name: str,
    output_root: Path,
    tracker_year: Optional[int] = None,
    tracker_month: Optional[int] = None,
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
            logger.exception("Processing failed", error_code="critical_abort")
            raise
        finally:
            # Remove the handler
            logger.remove(handler_id)
