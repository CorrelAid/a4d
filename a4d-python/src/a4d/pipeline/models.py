"""Pipeline result models for tracking processing outputs."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TrackerResult:
    """Result from processing a single tracker file.

    Attributes:
        tracker_file: Original tracker file path
        tracker_name: Base name without extension
        raw_output: Path to raw parquet file (None if extraction failed)
        cleaned_output: Path to cleaned parquet file (None if cleaning failed)
        success: Whether processing completed successfully
        error: Error message if processing failed
        cleaning_errors: Number of data quality errors during cleaning (type conversion,
                        validation failures, etc.). These are non-fatal - data is cleaned
                        with error values (999999, "Undefined", etc.)
        error_breakdown: Breakdown of errors by type (error_code → count).
                        Example: {"type_conversion": 10, "invalid_value": 5}
    """

    tracker_file: Path
    tracker_name: str
    raw_output: Path | None = None
    cleaned_output: Path | None = None
    success: bool = True
    error: str | None = None
    cleaning_errors: int = 0
    error_breakdown: dict[str, int] | None = None


@dataclass
class PipelineResult:
    """Result from running the complete patient pipeline.

    Attributes:
        tracker_results: Results from processing individual trackers
        tables: Dictionary mapping table name to output path
        total_trackers: Total number of trackers processed
        successful_trackers: Number of successfully processed trackers
        failed_trackers: Number of failed trackers
        success: Whether entire pipeline completed successfully
    """

    tracker_results: list[TrackerResult]
    tables: dict[str, Path]
    total_trackers: int
    successful_trackers: int
    failed_trackers: int
    success: bool

    @classmethod
    def from_tracker_results(
        cls,
        tracker_results: list[TrackerResult],
        tables: dict[str, Path] | None = None
    ) -> "PipelineResult":
        """Create PipelineResult from tracker results.

        Args:
            tracker_results: List of tracker processing results
            tables: Dictionary of created tables (empty if table creation skipped)

        Returns:
            PipelineResult with computed statistics
        """
        successful = sum(1 for r in tracker_results if r.success)
        failed = len(tracker_results) - successful

        return cls(
            tracker_results=tracker_results,
            tables=tables or {},
            total_trackers=len(tracker_results),
            successful_trackers=successful,
            failed_trackers=failed,
            success=failed == 0
        )
