"""Shared helpers for the source-vs-output validators."""

from __future__ import annotations

from typing import Any

import polars as pl

from a4d.clean.converters import safe_convert_column
from a4d.config import settings
from a4d.errors import ErrorCode, ErrorCollector

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

    ``safe_convert_column`` writes to its caller's ErrorCollector with code
    ``type_conversion``. We pass a sacrificial collector here so those entries
    don't pollute the validator's findings collector.
    """
    name = raw_col.name
    sacrificial = ErrorCollector()
    df = pl.DataFrame({name: raw_col})
    parsed = safe_convert_column(
        df=df,
        column=name,
        target_type=target_type,
        error_collector=sacrificial,
        # safe_convert_column reads file_name/patient_id for error attribution; we
        # don't care about the entries it generates, but the columns must exist.
        file_name_col="__unused_file__",
        patient_id_col="__unused_pid__",
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
    collector: ErrorCollector,
    *,
    file_name: str,
    patient_id: str,
    column: str,
    original_value: Any,
    error_message: str,
    error_code: ErrorCode,
    function_name: str,
) -> None:
    """Thin wrapper around ``ErrorCollector.add_error`` enforcing the schema.

    The collector accepts only the ErrorCode literal types — validator codes
    that don't fit (MISSING_ROW, VALUE_SHIFT, ...) are encoded in
    ``error_message`` and the underlying ``error_code`` is set to the closest
    existing literal. Caller must pass one of: ``"missing_value"`` for
    missing/phantom rows, ``"invalid_value"`` for shifts/range violations,
    ``"type_conversion"`` for parse-driven nulls.
    """
    collector.add_error(
        file_name=file_name,
        patient_id=patient_id,
        column=column,
        original_value="" if original_value is None else str(original_value),
        error_message=error_message,
        error_code=error_code,
        function_name=function_name,
        script="validate",
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
