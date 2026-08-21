"""Data quality error tracking for pipeline processing.

This module provides the ErrorCollector class for tracking conversion failures,
validation errors, and other data quality issues. Errors are exported as
parquet files and aggregated into the logs table for BigQuery analysis.

This is separate from operational logging (see a4d.logging) which tracks
pipeline execution and progress.
"""

from datetime import datetime
from typing import Any, Literal

import polars as pl
from pydantic import BaseModel, Field

# Error code types based on R pipeline
ErrorCode = Literal[
    "type_conversion",  # Failed to convert type (e.g., "abc" -> int)
    "invalid_value",  # Value outside allowed range or not in allowed list
    "missing_value",  # Required value is missing/NA
    "missing_required_field",  # Critical field (patient_id, status) is missing, row excluded
    "invalid_tracker",  # Tracker-level issues (missing columns, etc.)
    "function_call",  # Generic function execution error
    "critical_abort",  # Fatal error, tracker cannot be processed
    "typo_rescued",  # Known source-data typo substituted before parsing (informational)
    "source_formula_error",  # Source tracker's own formula errored (#NUM!, #DIV/0!) -- an
    # input it depended on was never recorded, so no value could be computed (informational)
    "balance_reconciliation",  # Recomputed closing stock disagrees with the balance the
    # tracker itself recorded -- the transactions and the recorded total do not add up
    "glucose_unit_swapped",  # A whole column labelled mg/dL holds mmol/L readings; values
    # moved to the mmol column and rescaled. Reported once per column, not per row
    "glucose_unit_suspect",  # A single reading sits where the other unit's values land;
    # kept as recorded, because a severe hypoglycaemic reading is indistinguishable
    "date_recovered_from_text",  # A date was read out of a clinical note rather than from a
    # date-shaped cell -- carries the note, so the extraction stays auditable (informational)
    "date_multiple_in_cell",  # The cell named several dates and the first was published;
    # a single date column cannot hold three admissions, so the workbook is what needs fixing
    "date_year_inferred",  # The cell named a day and a month but no year, so the tracker's
    # own year was used -- the one component published that the source does not state
]


class DataError(BaseModel):
    """Single data quality error record.

    Attributes:
        file_name: Name of the tracker file where error occurred
        patient_id: Patient ID (if applicable, else "unknown")
        column: Column name where error occurred
        original_value: Original value that caused the error
        error_message: Human-readable error description
        error_code: Error category for grouping/analysis
        script: Script name where error occurred (e.g., "script2", "clean")
        function_name: Function name where error occurred
        timestamp: When the error was recorded
    """

    file_name: str
    patient_id: str
    column: str
    original_value: str
    error_message: str
    error_code: ErrorCode
    script: str = "clean"
    function_name: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class ErrorCollector:
    """Collects data quality errors for export to parquet.

    Errors are collected during processing and exported as a DataFrame
    at the end. The DataFrame schema matches the logs table in BigQuery
    for easy querying and dashboard visualization.

    Example:
        >>> collector = ErrorCollector()
        >>> collector.add_error(
        ...     file_name="clinic_001.xlsx",
        ...     patient_id="XX_YY001",
        ...     column="age",
        ...     original_value="invalid",
        ...     error_message="Could not convert 'invalid' to Int32",
        ...     error_code="type_conversion",
        ...     function_name="safe_convert_column"
        ... )
        >>> # Or batch add:
        >>> errors = [
        ...     DataError(file_name="clinic_001.xlsx", patient_id="XX_YY001", ...),
        ...     DataError(file_name="clinic_001.xlsx", patient_id="XX_YY002", ...),
        ... ]
        >>> collector.add_errors(errors)
        >>> df = collector.to_dataframe()
        >>> df.write_parquet("output/clinic_001/errors.parquet")
    """

    def __init__(self):
        """Initialize an empty error collector."""
        self.errors: list[DataError] = []

    def add_error(
        self,
        file_name: str,
        patient_id: str,
        column: str,
        original_value: Any,
        error_message: str,
        error_code: ErrorCode,
        script: str = "clean",
        function_name: str = "",
    ) -> None:
        """Add a data quality error to the collector.

        Args:
            file_name: Name of the tracker file
            patient_id: Patient ID (use "unknown" if not applicable)
            column: Column name where error occurred
            original_value: Original value that caused the error
            error_message: Human-readable error description
            error_code: Error category (type_conversion, invalid_value, etc.)
            script: Script name (default: "clean")
            function_name: Function name where error occurred
        """
        error = DataError(
            file_name=file_name,
            patient_id=patient_id,
            column=column,
            original_value=str(original_value),
            error_message=error_message,
            error_code=error_code,
            script=script,
            function_name=function_name,
        )
        self.errors.append(error)

    def add_errors(self, errors: list[DataError]) -> None:
        """Add multiple errors at once.

        Args:
            errors: List of DataError instances to add

        Example:
            >>> errors = [
            ...     DataError(file_name="clinic_001.xlsx", patient_id="XX_YY001", ...),
            ...     DataError(file_name="clinic_001.xlsx", patient_id="XX_YY002", ...),
            ... ]
            >>> collector.add_errors(errors)
        """
        self.errors.extend(errors)

    def to_dataframe(self) -> pl.DataFrame:
        """Export errors as a Polars DataFrame for parquet export.

        Returns:
            Polars DataFrame with all error records, or empty DataFrame if no errors

        Schema:
            - file_name: str
            - patient_id: str
            - column: str
            - original_value: str
            - error_message: str
            - error_code: str (categorical)
            - script: str (categorical)
            - function_name: str (categorical)
            - timestamp: datetime
        """
        if not self.errors:
            # Return empty DataFrame with correct schema
            return pl.DataFrame(
                schema={
                    "file_name": pl.Utf8,
                    "patient_id": pl.Utf8,
                    "column": pl.Utf8,
                    "original_value": pl.Utf8,
                    "error_message": pl.Utf8,
                    "error_code": pl.Categorical,
                    "script": pl.Categorical,
                    "function_name": pl.Categorical,
                    "timestamp": pl.Datetime,
                }
            )

        # Convert Pydantic models to dict records
        records = [error.model_dump() for error in self.errors]

        # Create DataFrame and cast categorical columns for efficiency
        df = pl.DataFrame(records)
        df = df.with_columns(
            [
                pl.col("error_code").cast(pl.Categorical),
                pl.col("script").cast(pl.Categorical),
                pl.col("function_name").cast(pl.Categorical),
            ]
        )

        return df

    def __len__(self) -> int:
        """Return number of errors collected."""
        return len(self.errors)

    def __bool__(self) -> bool:
        """Return True if any errors have been collected."""
        return len(self.errors) > 0

    def clear(self) -> None:
        """Clear all collected errors."""
        self.errors.clear()

    def get_error_summary(self) -> dict[str, int]:
        """Get summary of errors by error_code.

        Returns:
            Dictionary mapping error_code to count

        Example:
            >>> collector.get_error_summary()
            {'type_conversion': 10, 'invalid_value': 5}
        """
        summary: dict[str, int] = {}
        for error in self.errors:
            summary[error.error_code] = summary.get(error.error_code, 0) + 1
        return summary
