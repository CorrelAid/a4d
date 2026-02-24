"""A4D Medical Tracker Data Processing Pipeline."""

from a4d.config import settings
from a4d.errors import DataError, ErrorCollector
from a4d.logging import file_logger, setup_logging

__version__ = "0.1.0"

__all__ = [
    "settings",
    "setup_logging",
    "file_logger",
    "ErrorCollector",
    "DataError",
]
