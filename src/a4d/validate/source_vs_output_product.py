"""Source-vs-output validation for the product pipeline.

Group-granularity checks only in v1: per-cell checks would require reproducing
cleaning steps 2.0-2.5 to reconstruct the per-(sheet, product) row index, which
we deliberately avoid (see the plan at
``C:/Users/furin/.claude/plans/output-vs-source-validation-swirling-nygaard.md``).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from loguru import logger

from a4d.errors import ErrorCollector
from a4d.validate.common import emit_finding

GROUP_KEY = ["file_name", "product_sheet_name", "product"]

# Threshold for COLUMN_NULL_RATE_DELTA: emit a finding if cleaned null rate
# exceeds raw null rate by more than this fraction (5 percentage points).
NULL_RATE_DELTA_THRESHOLD = 0.05


def _explode_multi_product_cells(df: pl.DataFrame) -> pl.DataFrame:
    """Mirror clean/product.py:169-242 (the row-changing part only).

    Splits ``product`` on '; ' and ' and ', then ``.explode()``. We deliberately
    skip the parenthetical-units extraction because it doesn't change row count
    or the join keys.
    """
    if "product" not in df.columns:
        return df
    df = df.with_columns(
        pl.col("product").cast(pl.Utf8).str.replace_all(" and ", "; ").alias("product")
    )
    return df.with_columns(pl.col("product").str.split("; ")).explode("product")


def _load_raw(run_dir: Path) -> pl.DataFrame | None:
    raw_dir = run_dir / "product_data_raw"
    if not raw_dir.exists():
        return None
    files = sorted(raw_dir.glob("*_product_raw.parquet"))
    if not files:
        return None
    frames = [pl.read_parquet(f) for f in files]
    return pl.concat(frames, how="diagonal")


def _load_cleaned(run_dir: Path) -> pl.DataFrame | None:
    path = run_dir / "tables" / "product_data.parquet"
    if not path.exists():
        return None
    return pl.read_parquet(path)


def check_missing_groups(
    raw_exploded: pl.DataFrame, cleaned: pl.DataFrame, collector: ErrorCollector
) -> None:
    """MISSING_GROUP + PHANTOM_GROUP: anti-joins on (file, sheet, product)."""
    raw_keys = raw_exploded.filter(pl.col("product").is_not_null()).select(GROUP_KEY).unique()
    cleaned_keys = cleaned.filter(pl.col("product").is_not_null()).select(GROUP_KEY).unique()

    missing = raw_keys.join(cleaned_keys, on=GROUP_KEY, how="anti")
    for row in missing.iter_rows(named=True):
        emit_finding(
            collector,
            file_name=row["file_name"] or "",
            patient_id="",
            column="__group__",
            original_value=f"{row['product_sheet_name']}|{row['product']}",
            error_message=(
                f"MISSING_GROUP: raw (sheet={row['product_sheet_name']}, "
                f"product={row['product']!r}) absent in cleaned product_data"
            ),
            error_code="missing_value",
            function_name="check_missing_groups",
        )

    phantom = cleaned_keys.join(raw_keys, on=GROUP_KEY, how="anti")
    for row in phantom.iter_rows(named=True):
        emit_finding(
            collector,
            file_name=row["file_name"] or "",
            patient_id="",
            column="__group__",
            original_value=f"{row['product_sheet_name']}|{row['product']}",
            error_message=(
                f"PHANTOM_GROUP: cleaned (sheet={row['product_sheet_name']}, "
                f"product={row['product']!r}) has no matching raw source"
            ),
            error_code="missing_value",
            function_name="check_missing_groups",
        )


def check_row_count_delta(
    raw_exploded: pl.DataFrame, cleaned: pl.DataFrame, collector: ErrorCollector
) -> None:
    """ROW_COUNT_DELTA: per-group row counts raw vs cleaned.

    Reported as a magnitude with no judgment about right/wrong — the cleaner
    legitimately drops uninformative rows. Reviewers triage.
    """
    raw_counts = (
        raw_exploded.filter(pl.col("product").is_not_null())
        .group_by(GROUP_KEY)
        .len()
        .rename({"len": "raw_count"})
    )
    cleaned_counts = (
        cleaned.filter(pl.col("product").is_not_null())
        .group_by(GROUP_KEY)
        .len()
        .rename({"len": "cleaned_count"})
    )
    joined = raw_counts.join(cleaned_counts, on=GROUP_KEY, how="inner")
    deltas = joined.filter(pl.col("raw_count") != pl.col("cleaned_count"))

    for row in deltas.iter_rows(named=True):
        delta = row["cleaned_count"] - row["raw_count"]
        emit_finding(
            collector,
            file_name=row["file_name"] or "",
            patient_id="",
            column="__group__",
            original_value=f"raw={row['raw_count']}|cleaned={row['cleaned_count']}",
            error_message=(
                f"ROW_COUNT_DELTA: (sheet={row['product_sheet_name']}, "
                f"product={row['product']!r}) raw={row['raw_count']} "
                f"cleaned={row['cleaned_count']} delta={delta:+d}"
            ),
            error_code="invalid_value",
            function_name="check_row_count_delta",
        )


def check_column_null_rate_delta(
    raw: pl.DataFrame, cleaned: pl.DataFrame, collector: ErrorCollector
) -> None:
    """COLUMN_NULL_RATE_DELTA: per-column null rate raw vs cleaned across the run.

    Emit one finding per column where cleaned null rate exceeds raw null rate
    by >NULL_RATE_DELTA_THRESHOLD. Coarse, but surfaces silent column-wide losses.
    """
    raw_total = raw.height
    cleaned_total = cleaned.height
    if raw_total == 0 or cleaned_total == 0:
        return

    common = [c for c in cleaned.columns if c in raw.columns]
    for col in common:
        raw_null_rate = raw[col].null_count() / raw_total
        cleaned_null_rate = cleaned[col].null_count() / cleaned_total
        delta = cleaned_null_rate - raw_null_rate
        if delta > NULL_RATE_DELTA_THRESHOLD:
            emit_finding(
                collector,
                file_name="",
                patient_id="",
                column=col,
                original_value=f"raw_null_rate={raw_null_rate:.3f}",
                error_message=(
                    f"COLUMN_NULL_RATE_DELTA: column={col!r} "
                    f"raw_null_rate={raw_null_rate:.3f} "
                    f"cleaned_null_rate={cleaned_null_rate:.3f} "
                    f"delta={delta:+.3f}"
                ),
                error_code="invalid_value",
                function_name="check_column_null_rate_delta",
            )


def validate_product_run(run_dir: Path) -> ErrorCollector | None:
    """Run the four product checks. Returns None if no product output exists."""
    raw = _load_raw(run_dir)
    cleaned = _load_cleaned(run_dir)
    if raw is None or cleaned is None:
        logger.info(f"Product pipeline outputs not found in {run_dir}; skipping.")
        return None

    collector = ErrorCollector()
    raw_exploded = _explode_multi_product_cells(raw)
    logger.info(
        f"Product validation: raw={raw.shape} (exploded={raw_exploded.shape}), "
        f"cleaned={cleaned.shape}"
    )

    check_missing_groups(raw_exploded, cleaned, collector)
    check_row_count_delta(raw_exploded, cleaned, collector)
    check_column_null_rate_delta(raw, cleaned, collector)

    logger.info(f"Product validation: {len(collector)} findings")
    return collector
