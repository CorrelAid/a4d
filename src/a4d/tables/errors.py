"""Create errors table from data quality errors collected during pipeline processing.

Aggregates all DataError records from tracker results into a single parquet file
for BigQuery upload and dashboard analysis.
"""

from pathlib import Path

import polars as pl
from loguru import logger

from a4d.errors import DataError


def create_table_errors(data_errors: list[DataError], output_dir: Path) -> Path:
    """Create errors table from all data quality errors across all trackers.

    Args:
        data_errors: All DataError records collected during pipeline processing
        output_dir: Directory to write the errors table parquet

    Returns:
        Path to created errors table parquet file

    Example:
        >>> errors_path = create_table_errors(all_errors, Path("output/tables"))
        >>> errors_path
        Path('output/tables/table_errors.parquet')
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "table_errors.parquet"

    if not data_errors:
        logger.info("No data quality errors to write, creating empty errors table")
        pl.DataFrame(
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
        ).write_parquet(output_file)
        return output_file

    records = [e.model_dump() for e in data_errors]
    df = pl.DataFrame(records).with_columns(
        pl.col("error_code").cast(pl.Categorical),
        pl.col("script").cast(pl.Categorical),
        pl.col("function_name").cast(pl.Categorical),
    ).sort("timestamp")

    df.write_parquet(output_file)

    logger.info(f"Errors table saved: {output_file} ({len(df):,} records)")

    breakdown = df.group_by("error_code").agg(pl.len().alias("count")).sort("count", descending=True)
    logger.info(f"Error breakdown: {breakdown.to_dict(as_series=False)}")

    return output_file
