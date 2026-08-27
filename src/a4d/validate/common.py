"""Shared helpers for the source-vs-output validators."""

from __future__ import annotations

from typing import Any

import polars as pl

from a4d.clean.converters import safe_convert_column
from a4d.config import settings
from a4d.findings import Arm, ErrorCode, findings_discarded, report_finding

# Mirrors clean/patient.py:241-256. Hyphen->underscore happens first, then we
# extract the leading "LETTERS_NON-UNDERSCORE-CHARS" group. Single-token IDs
# (no underscore) pass through unchanged.
_NORMALIZE_REGEX = r"^([A-Z]+_[^_]+)"


def normalize_patient_id(col: pl.Expr) -> pl.Expr:
    """Replicate the patient_id normalization in clean/patient.py:241-256.

    Returns an expression — caller wraps it in ``with_columns``.
    """
    hyphen_to_underscore = col.str.replace_all("-", "_")
    return (
        pl.when(hyphen_to_underscore.str.contains("_"))
        .then(hyphen_to_underscore.str.extract(_NORMALIZE_REGEX, 1))
        .otherwise(hyphen_to_underscore)
    )


def safe_parse_series(
    raw_col: pl.Series,
    target_type: pl.DataType | type[pl.DataType],
) -> pl.Series:
    """Re-parse a raw string Series to ``target_type``, discarding parse errors.

    ``safe_convert_column`` reports a ``type_conversion`` finding for every
    cell it cannot parse. Here those findings are about the validator's own
    probe rather than about a workbook, so the block discards them explicitly.
    """
    name = raw_col.name
    df = pl.DataFrame({name: raw_col})
    with findings_discarded():
        parsed = safe_convert_column(
            df=df,
            column=name,
            target_type=target_type,
        )
    series = parsed[name]
    # safe_convert_column writes settings.error_val_numeric / error_val_character /
    # error_val_date for parse failures; map those sentinels back to null so the
    # validator can cleanly distinguish "parsed" from "failed to parse".
    if series.dtype.is_numeric():
        return series.replace({settings.error_val_numeric: None})
    if series.dtype in (pl.Utf8, pl.String):
        return series.replace({settings.error_val_character: None})
    if series.dtype == pl.Date:
        sentinel_date = pl.Series("_s", [settings.error_val_date]).str.to_date()[0]
        return series.replace({sentinel_date: None})
    return series


def emit_finding(
    *,
    file_name: str,
    arm: Arm = "patient",
    patient_id: str,
    column: str,
    original_value: Any,
    error_message: str,
    error_code: ErrorCode,
    function_name: str,
    sheet_name: str = "",
    tracker_month: int | None = None,
) -> None:
    """Thin wrapper around ``report_finding`` enforcing the schema.

    Caller must pass one of: ``"source_row_not_in_output"`` for missing or
    phantom rows, ``"value_out_of_range"`` for shifts and range violations,
    ``"type_conversion"`` for parse-driven nulls. The first exists for this
    tool specifically -- an earlier version borrowed whichever operator-facing
    code was closest and encoded the real one in the message, which is the
    mis-filing this taxonomy now forbids.

    Every code this wrapper accepts is row-scoped, so the caller has to name
    the sheet the row came from -- the frames it walks all carry it.
    """
    report_finding(
        file_name=file_name,
        arm=arm,
        patient_id=patient_id,
        column=column,
        original_value="" if original_value is None else str(original_value),
        message=error_message,
        error_code=error_code,
        sheet_name=sheet_name,
        tracker_month=tracker_month,
        function_name=function_name,
        stage="validate",
    )


def is_close(
    a: float | None, b: float | None, *, abs_tol: float = 1e-6, rel_tol: float = 1e-4
) -> bool:
    """Null-aware float comparison with abs and relative tolerance.

    Both null -> equal. Either-side null -> not equal.
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    diff = abs(a - b)
    if diff <= abs_tol:
        return True
    scale = max(abs(a), abs(b))
    return diff <= rel_tol * scale
