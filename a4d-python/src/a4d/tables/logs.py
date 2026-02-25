"""Create logs table from pipeline execution logs.

This module reads all JSON-formatted log files created by the pipeline
and creates a structured table for BigQuery upload and dashboard analysis.

Log files are created by loguru with serialize=True, producing JSON lines format.
Each line contains structured data about pipeline execution: timestamps, levels,
messages, source locations, exceptions, and custom context fields.
"""

import json
from pathlib import Path

import polars as pl
from loguru import logger


def parse_log_file(log_file: Path) -> pl.DataFrame:
    """Parse a single JSON lines log file into a DataFrame.

    Args:
        log_file: Path to .log file (JSON lines format from loguru)

    Returns:
        DataFrame with parsed log records, or empty DataFrame if file is invalid

    Example:
        >>> df = parse_log_file(Path("output/logs/2024_Penang_patient.log"))
        >>> df.columns
        ['timestamp', 'level', 'message', 'log_file', ...]
    """
    records = []

    try:
        with open(log_file, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                try:
                    log_entry = json.loads(line)
                    record_data = log_entry.get("record", {})

                    # Extract timestamp
                    time_data = record_data.get("time", {})
                    timestamp = time_data.get("timestamp")

                    # Extract level
                    level_data = record_data.get("level", {})
                    level = level_data.get("name", "UNKNOWN")

                    # Extract message
                    message = record_data.get("message", "")

                    # Extract source location
                    file_data = record_data.get("file", {})
                    source_file = file_data.get("name", "")
                    source_path = file_data.get("path", "")

                    function = record_data.get("function", "")
                    line = record_data.get("line", 0)
                    module = record_data.get("module", "")

                    # Extract context fields (file_name, tracker_year, tracker_month)
                    extra = record_data.get("extra", {})
                    file_name = extra.get("file_name")
                    tracker_year = extra.get("tracker_year")
                    tracker_month = extra.get("tracker_month")

                    # Extract process info (useful for debugging parallel processing)
                    process_data = record_data.get("process", {})
                    process_name = process_data.get("name", "")

                    # Extract exception info if present
                    exception = record_data.get("exception")
                    has_exception = exception is not None
                    exception_type = None
                    exception_value = None

                    if has_exception and exception:
                        exception_type = exception.get("type")
                        exception_value = exception.get("value")

                    # Create record
                    records.append(
                        {
                            "timestamp": timestamp,
                            "level": level,
                            "message": message,
                            "log_file": log_file.name,
                            "file_name": file_name,
                            "tracker_year": tracker_year,
                            "tracker_month": tracker_month,
                            "source_file": source_file,
                            "source_path": source_path,
                            "function": function,
                            "line": line,
                            "module": module,
                            "process_name": process_name,
                            "has_exception": has_exception,
                            "exception_type": exception_type,
                            "exception_value": exception_value,
                        }
                    )

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON in {log_file.name}:{line_num}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing line {line_num} in {log_file.name}: {e}")
                    continue

    except Exception as e:
        logger.error(f"Failed to read log file {log_file.name}: {e}")
        return pl.DataFrame()

    if not records:
        return pl.DataFrame()

    # Create DataFrame with proper types
    df = pl.DataFrame(records)

    # Cast categorical columns for efficiency
    df = df.with_columns(
        [
            pl.col("level").cast(pl.Categorical),
            pl.col("log_file").cast(pl.Categorical),
            pl.col("source_file").cast(pl.Categorical),
            pl.col("function").cast(pl.Categorical),
            pl.col("module").cast(pl.Categorical),
            pl.col("process_name").cast(pl.Categorical),
        ]
    )

    return df


def create_table_logs(logs_dir: Path, output_dir: Path) -> Path:
    """Create logs table from all pipeline log files.

    Reads all .log files from the logs directory, parses JSON lines,
    and creates a structured table for BigQuery upload.

    Args:
        logs_dir: Directory containing .log files (e.g., output/logs/)
        output_dir: Directory to write the logs table parquet

    Returns:
        Path to created logs table parquet file

    Example:
        >>> logs_path = create_table_logs(
        ...     Path("output/logs"),
        ...     Path("output/tables")
        ... )
        >>> logs_path
        Path('output/tables/table_logs.parquet')
    """
    logger.info(f"Creating logs table from: {logs_dir}")

    # Find all .log files (exclude .zip compressed files)
    log_files = sorted(logs_dir.glob("*.log"))
    logger.info(f"Found {len(log_files)} log files to process")

    if not log_files:
        logger.warning("No log files found, creating empty logs table")
        # Create empty DataFrame with correct schema
        empty_df = pl.DataFrame(
            schema={
                "timestamp": pl.Datetime,
                "level": pl.Categorical,
                "message": pl.Utf8,
                "log_file": pl.Categorical,
                "file_name": pl.Utf8,
                "tracker_year": pl.Int32,
                "tracker_month": pl.Int32,
                "source_file": pl.Categorical,
                "source_path": pl.Utf8,
                "function": pl.Categorical,
                "line": pl.Int32,
                "module": pl.Categorical,
                "process_name": pl.Categorical,
                "has_exception": pl.Boolean,
                "exception_type": pl.Utf8,
                "exception_value": pl.Utf8,
            }
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "table_logs.parquet"
        empty_df.write_parquet(output_file)
        return output_file

    # Parse all log files
    all_logs = []
    for log_file in log_files:
        logger.debug(f"Parsing: {log_file.name}")
        df = parse_log_file(log_file)
        if len(df) > 0:
            all_logs.append(df)

    logs_table = pl.concat(all_logs, how="vertical")

    # Sort by timestamp for chronological analysis
    logs_table = logs_table.sort("timestamp")

    logger.info(f"Created logs table with {len(logs_table)} records")
    logger.info(f"Date range: {logs_table['timestamp'].min()} to {logs_table['timestamp'].max()}")

    # Log summary by level
    level_counts = logs_table.group_by("level").agg(pl.len()).sort("level")
    logger.info(f"Log level distribution: {level_counts.to_dict(as_series=False)}")

    # Write to parquet
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "table_logs.parquet"
    logs_table.write_parquet(output_file)

    logger.info(f"Logs table saved: {output_file}")
    logger.info(f"Table size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")

    return output_file
