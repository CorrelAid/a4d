"""Product table creation.

Covers R Script 3 (steps 3.1-3.3): merge all cleaned product parquets into
a single ``product_data`` table with the canonical 19-column schema.
"""

from pathlib import Path

import polars as pl
from loguru import logger

from a4d.clean.converters import safe_convert_column
from a4d.clean.schema_product import apply_schema, get_product_data_schema
from a4d.clean.validators import fix_patient_id
from a4d.errors import ErrorCollector


def read_cleaned_product_data(cleaned_files: list[Path]) -> pl.DataFrame:
    """Step 3.1 — read and diagonally concatenate cleaned product parquets.

    Uses ``pl.concat(..., how="diagonal")`` so trackers with missing columns
    are filled with nulls rather than dropped.

    Args:
        cleaned_files: List of cleaned product parquet paths.

    Returns:
        Single DataFrame with the union of all tracker columns.
    """
    if not cleaned_files:
        raise ValueError("No cleaned product files provided")

    dfs = [pl.read_parquet(file) for file in cleaned_files]
    return pl.concat(dfs, how="diagonal")


def create_table_product_data(cleaned_files: list[Path], output_dir: Path) -> Path:
    """Build the final ``product_data`` table from cleaned tracker parquets.

    Covers R steps 3.1-3.3:
    1. Concatenate every cleaned product parquet.
    2. Preserve ``product_released_to`` as ``orig_product_released_to`` and
       normalise ``product_released_to`` via ``fix_patient_id``.
    3. Apply the 19-column product schema with type enforcement; values that
       fail conversion are replaced by the error sentinels from ``settings``.

    Args:
        cleaned_files: Cleaned product parquet files from Script 2.
        output_dir: Directory where ``product_data.parquet`` is written.

    Returns:
        Path to the written ``product_data.parquet`` file.
    """
    df = read_cleaned_product_data(cleaned_files)

    df = df.with_columns(
        pl.col("product_released_to").alias("orig_product_released_to")
    )

    error_collector = ErrorCollector()
    df = fix_patient_id(
        df=df,
        error_collector=error_collector,
        patient_id_col="product_released_to",
    )

    # Adds any missing schema columns as typed nulls so the cast loop below
    # has every target column available; safe_convert_column preserves order.
    df = apply_schema(df)

    schema = get_product_data_schema()
    for col, dtype in schema.items():
        if dtype in (pl.Int32, pl.Int64, pl.Float32, pl.Float64, pl.Date):
            df = safe_convert_column(
                df=df,
                column=col,
                target_type=dtype,
                error_collector=error_collector,
                patient_id_col="product_released_to",
            )

    # Surface any errors collected by fix_patient_id / safe_convert_column at
    # the table-aggregation stage. These run outside any per-tracker file_logger,
    # so without this loop the errors disappear silently.
    for err in error_collector.errors:
        logger.bind(
            error_code=err.error_code,
            script="script3",
            function_name=err.function_name,
            file_name=err.file_name,
            column=err.column,
        ).warning(
            f"Table-stage error: {err.error_message} "
            f"(file={err.file_name}, column={err.column}, value={err.original_value})"
        )
    if error_collector.errors:
        logger.info(f"Table-stage errors: {len(error_collector.errors)}")

    logger.info(f"Product data table dimensions: {df.shape}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "product_data.parquet"
    df.write_parquet(output_path)

    return output_path


def link_product_patient(
    product_df: pl.DataFrame,
    patient_static_path: Path,
) -> int:
    """Validate product_released_to against patient_data_static.

    LEFT-joins product rows onto the patient table on
    ``(file_name, product_released_to ↔ patient_id)`` and logs each
    ``(file_name, product_released_to)`` pair that has no patient match.
    Logging-only — does not modify either table and never raises.

    Mirrors R's ``script3_link_product_patient.R`` with one deviation:
    rows where ``product_released_to`` is null or equals the
    ``error_val_character`` sentinel ("Undefined") are filtered out
    before joining. Those are not real patient IDs and would flood the
    log with non-issues.

    Args:
        product_df: Product table (post-``fix_patient_id``).
        patient_static_path: Path to ``patient_data_static.parquet``.

    Returns:
        Total count of mismatched product rows for telemetry/test use.
    """
    from a4d.config import settings

    if not patient_static_path.exists():
        logger.warning(
            f"Patient table not available at {patient_static_path}; "
            "skipping product-patient link validation."
        )
        return 0

    patient_keys = (
        pl.read_parquet(patient_static_path)
        .select(["file_name", "patient_id"])
        .with_columns(pl.lit(True).alias("_patient_matched"))
    )

    sentinel = settings.error_val_character
    candidates = product_df.filter(
        pl.col("product_released_to").is_not_null()
        & (pl.col("product_released_to") != sentinel)
    )

    joined = candidates.join(
        patient_keys,
        left_on=["file_name", "product_released_to"],
        right_on=["file_name", "patient_id"],
        how="left",
    )
    mismatches = joined.filter(pl.col("_patient_matched").is_null())

    mismatch_groups = (
        mismatches.group_by(["file_name", "product_released_to"])
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
    )

    total_mismatched_rows = mismatches.height
    distinct_pairs = mismatch_groups.height
    total_examined = candidates.height

    for row in mismatch_groups.iter_rows(named=True):
        logger.warning(
            f"Unmatched product_released_to: file_name='{row['file_name']}' "
            f"product_id='{row['product_released_to']}' count={row['count']}"
        )

    logger.info(
        f"Product-patient link validation: {total_mismatched_rows} mismatched rows, "
        f"{distinct_pairs} distinct (file × id) pairs, "
        f"{total_examined} candidate product rows examined."
    )

    return total_mismatched_rows
