"""Source-vs-output validation for the patient pipeline.

See ``C:/Users/furin/.claude/plans/output-vs-source-validation-swirling-nygaard.md``
for the design rationale and the catalog of checks.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from loguru import logger

from a4d.clean.validators import load_numeric_ranges
from a4d.errors import ErrorCollector
from a4d.validate.common import (
    emit_finding,
    is_close,
    normalize_patient_id,
    safe_parse_series,
)

# Columns whose values the cleaner re-derives or transforms. Excluded from
# VALUE_SHIFT comparisons.
DERIVED_COLUMNS = frozenset({"age", "bmi", "t1d_diagnosis_age"})

# Columns the cleaner converts (height: cm->m; FBG: mmol<->mg). Excluded from
# VALUE_SHIFT in v1; promoted to a follow-up.
UNIT_CONVERTED_COLUMNS = frozenset({"height", "fbg_updated_mg", "fbg_updated_mmol"})

# Join key for row-level checks. Mirrors patient_data_monthly's natural grain.
ROW_KEY = ["clinic_id", "patient_id", "tracker_year", "tracker_month"]


def _load_raw(run_dir: Path) -> pl.DataFrame | None:
    """Concatenate all per-tracker raw patient parquets in the run directory."""
    raw_dir = run_dir / "patient_data_raw"
    if not raw_dir.exists():
        return None
    files = sorted(raw_dir.glob("*_patient_raw.parquet"))
    if not files:
        return None
    frames = [pl.read_parquet(f) for f in files]
    return pl.concat(frames, how="diagonal")


def _load_cleaned_monthly(run_dir: Path) -> pl.DataFrame | None:
    path = run_dir / "tables" / "patient_data_monthly.parquet"
    if not path.exists():
        return None
    return pl.read_parquet(path)


def _normalize_join_keys(df: pl.DataFrame) -> pl.DataFrame:
    """Apply patient_id normalization and cast year/month for clean joins."""
    out = df.with_columns(normalize_patient_id(pl.col("patient_id")).alias("patient_id"))
    return out.with_columns(
        [
            pl.col("tracker_year").cast(pl.Int64, strict=False),
            pl.col("tracker_month").cast(pl.Int64, strict=False),
        ]
    )


def check_missing_patients(
    raw: pl.DataFrame, cleaned: pl.DataFrame, collector: ErrorCollector
) -> None:
    """MISSING_ROW + PHANTOM_ROW: anti-joins on the normalized row key."""
    raw_keys = _normalize_join_keys(raw).select(ROW_KEY).unique()
    cleaned_keys = _normalize_join_keys(cleaned).select(ROW_KEY).unique()

    missing = raw_keys.join(cleaned_keys, on=ROW_KEY, how="anti")
    for row in missing.iter_rows(named=True):
        emit_finding(
            collector,
            file_name="",
            patient_id=row["patient_id"] or "unknown",
            column="__row__",
            original_value=f"{row['clinic_id']}|{row['tracker_year']}|{row['tracker_month']}",
            error_message=(
                f"MISSING_ROW: raw row for {row['patient_id']} "
                f"({row['tracker_year']}-{row['tracker_month']:02d}) "
                f"not found in cleaned patient_data_monthly"
            ),
            error_code="missing_value",
            function_name="check_missing_patients",
        )

    phantom = cleaned_keys.join(raw_keys, on=ROW_KEY, how="anti")
    for row in phantom.iter_rows(named=True):
        emit_finding(
            collector,
            file_name="",
            patient_id=row["patient_id"] or "unknown",
            column="__row__",
            original_value=f"{row['clinic_id']}|{row['tracker_year']}|{row['tracker_month']}",
            error_message=(
                f"PHANTOM_ROW: cleaned row for {row['patient_id']} "
                f"({row['tracker_year']}-{row['tracker_month']:02d}) "
                f"has no matching raw source"
            ),
            error_code="missing_value",
            function_name="check_missing_patients",
        )


def _join_for_cell_checks(raw: pl.DataFrame, cleaned: pl.DataFrame) -> pl.DataFrame:
    """Inner join raw and cleaned on the normalized row key.

    Suffixes raw columns with ``_raw`` and cleaned columns with ``_clean``;
    the join key columns are deduplicated under their original names.
    """
    raw_n = _normalize_join_keys(raw)
    cleaned_n = _normalize_join_keys(cleaned)

    raw_renamed = raw_n.rename({c: f"{c}_raw" for c in raw_n.columns if c not in ROW_KEY})
    cleaned_renamed = cleaned_n.rename(
        {c: f"{c}_clean" for c in cleaned_n.columns if c not in ROW_KEY}
    )
    return raw_renamed.join(cleaned_renamed, on=ROW_KEY, how="inner")


def check_unexpected_nulls(
    joined: pl.DataFrame, collector: ErrorCollector, file_name_col: str = "file_name_raw"
) -> None:
    """UNEXPECTED_NULL: raw cell non-empty, cleaned cell null.

    Each finding carries a ``was_parseable`` indicator in the message so
    reviewers can filter to surprising cases (raw value parsed cleanly but the
    cleaned cell is still null).
    """
    cleaned_cols = [c for c in joined.columns if c.endswith("_clean")]
    for clean_col in cleaned_cols:
        base = clean_col[: -len("_clean")]
        raw_col = f"{base}_raw"
        if raw_col not in joined.columns:
            continue

        target_dtype = joined.schema[clean_col]
        # null in cleaned, non-empty (after strip) in raw
        raw_str = pl.col(raw_col).cast(pl.Utf8).str.strip_chars()
        suspect = joined.filter(
            pl.col(clean_col).is_null() & raw_str.is_not_null() & (raw_str.str.len_chars() > 0)
        )
        if suspect.is_empty():
            continue

        # Determine parseability for this column once via the sacrificial parser.
        if target_dtype.is_numeric() or target_dtype == pl.Date or target_dtype == pl.Boolean:
            parsed = safe_parse_series(suspect[raw_col].cast(pl.Utf8), target_dtype)
        else:
            parsed = suspect[raw_col].cast(pl.Utf8)

        for row, parsed_val in zip(suspect.iter_rows(named=True), parsed.to_list(), strict=True):
            was_parseable = parsed_val is not None
            emit_finding(
                collector,
                file_name=row.get(file_name_col) or "",
                patient_id=row.get("patient_id") or "unknown",
                column=base,
                original_value=row[raw_col],
                error_message=(
                    f"UNEXPECTED_NULL: raw={row[raw_col]!r} cleaned=null "
                    f"was_parseable={was_parseable}"
                ),
                error_code="missing_value",
                function_name="check_unexpected_nulls",
            )


def check_value_shifts(
    joined: pl.DataFrame, collector: ErrorCollector, file_name_col: str = "file_name_raw"
) -> None:
    """VALUE_SHIFT: numeric, non-derived, non-unit-converted columns only.

    For each eligible column, re-parse raw via the sacrificial converter and
    compare to cleaned with abs/rel tolerance.
    """
    for clean_col in [c for c in joined.columns if c.endswith("_clean")]:
        base = clean_col[: -len("_clean")]
        if base in DERIVED_COLUMNS or base in UNIT_CONVERTED_COLUMNS:
            continue
        raw_col = f"{base}_raw"
        if raw_col not in joined.columns:
            continue
        clean_dtype = joined.schema[clean_col]
        if not clean_dtype.is_numeric():
            continue

        # Subset to rows where both sides have content; let the sacrificial
        # parser handle the empty/whitespace -> null normalization.
        subset = joined.select([raw_col, clean_col, "patient_id", file_name_col])
        parsed_raw = safe_parse_series(subset[raw_col].cast(pl.Utf8), clean_dtype)

        cleaned_vals = subset[clean_col].to_list()
        raw_vals = parsed_raw.to_list()
        pids = subset["patient_id"].to_list()
        files = subset[file_name_col].to_list()

        for raw_v, clean_v, pid, fname in zip(raw_vals, cleaned_vals, pids, files, strict=True):
            # Both null is fine; one-sided null is captured by other checks.
            if raw_v is None or clean_v is None:
                continue
            if is_close(float(raw_v), float(clean_v)):
                continue
            emit_finding(
                collector,
                file_name=fname or "",
                patient_id=pid or "unknown",
                column=base,
                original_value=raw_v,
                error_message=f"VALUE_SHIFT: raw={raw_v} cleaned={clean_v}",
                error_code="invalid_value",
                function_name="check_value_shifts",
            )


def _apply_height_auto_conversion(s: pl.Series) -> pl.Series:
    """Mirror clean/patient.py:530-535: divide values >2.3 by 100."""
    return pl.Series(
        s.name,
        [None if v is None else (v / 100.0 if v > 2.3 else v) for v in s.to_list()],
        dtype=pl.Float64,
    )


def check_out_of_range(
    raw: pl.DataFrame, collector: ErrorCollector, file_name_col: str = "file_name"
) -> None:
    """OUT_OF_RANGE_RAW: raw values outside the YAML numeric_ranges.

    Runs against the raw frame because the cleaner replaces out-of-range
    values with the sentinel before they reach the cleaned table. ``height``
    has the cm->m auto-conversion applied first to mirror the cleaner.
    """
    ranges = load_numeric_ranges()
    raw_n = _normalize_join_keys(raw)
    for column, bounds in ranges.items():
        if column not in raw_n.columns:
            continue
        parsed = safe_parse_series(raw_n[column].cast(pl.Utf8), pl.Float64)
        if column == "height":
            parsed = _apply_height_auto_conversion(parsed)

        min_v = float(bounds["min"])
        max_v = float(bounds["max"])

        pids = raw_n["patient_id"].to_list()
        files = (
            raw_n[file_name_col].to_list()
            if file_name_col in raw_n.columns
            else [""] * raw_n.height
        )
        for v, pid, fname in zip(parsed.to_list(), pids, files, strict=True):
            if v is None:
                continue
            if v < min_v or v > max_v:
                emit_finding(
                    collector,
                    file_name=fname or "",
                    patient_id=pid or "unknown",
                    column=column,
                    original_value=v,
                    error_message=(f"OUT_OF_RANGE_RAW: value {v} outside [{min_v}, {max_v}]"),
                    error_code="invalid_value",
                    function_name="check_out_of_range",
                )


def validate_patient_run(run_dir: Path) -> ErrorCollector | None:
    """Run all four patient checks against a pipeline run directory.

    Returns ``None`` if the run does not contain patient pipeline outputs
    (e.g. V5 is product-only).
    """
    raw = _load_raw(run_dir)
    cleaned = _load_cleaned_monthly(run_dir)
    if raw is None or cleaned is None:
        logger.info(f"Patient pipeline outputs not found in {run_dir}; skipping.")
        return None

    collector = ErrorCollector()
    logger.info(f"Patient validation: raw={raw.shape}, cleaned_monthly={cleaned.shape}")

    check_missing_patients(raw, cleaned, collector)
    joined = _join_for_cell_checks(raw, cleaned)
    check_unexpected_nulls(joined, collector)
    check_value_shifts(joined, collector)
    check_out_of_range(raw, collector)

    logger.info(f"Patient validation: {len(collector)} findings")
    return collector
