"""Resolve glucose readings recorded in the wrong unit.

The trackers carry fasting blood glucose in unit-specific columns, but the unit
a clinic actually records in does not always match the header it records under.
A4D's medical advisor confirmed (2026-08-17) the analytical limits of the
machines involved and authorised correcting a reading "if it is clearly a wrong
unit mixed up" -- which makes the question where "clearly" stops.

Measured across all 254 trackers, the confusion is overwhelmingly *per column*
rather than per row, and it clusters by clinic: 29 file-column groups have
nine tenths or more of their readings in mmol territory under an mg/dL header
(``2025_Kantha Bopha II``'s updated FBG is 99.8% of 951 readings), which cannot
be a run of severe hypoglycaemia. A single low reading in an otherwise ordinary
column is a different matter -- a genuine severe hypo and a mis-entered unit
look identical -- so those are flagged and left alone. Converting them would
multiply the clinically most important readings in the file by 18 and hide them.
"""

import polars as pl

from a4d.findings import report_finding

# mmol/L * 18 = mg/dL. The pipeline's existing cross-derivation uses the same
# rounded factor, so unit resolution stays consistent with it.
MMOL_TO_MG_FACTOR = 18.0

# A reading below this in an mg/dL column lands exactly where a mmol/L number
# would. It is not by itself impossible -- the advisor's mg/dL analytical floor
# is ~2-5 -- which is why it only ever triggers suspicion, never a row-level
# conversion.
MMOL_MG_BOUNDARY = 30.0

# A column is taken to be recorded in mmol/L only when nearly all of it reads
# that way. The measured distribution is strongly bimodal: 29 groups sit above
# 0.9 and 300 sit at 0.0, with the 0.5-0.9 band being per-patient mixing inside
# one column at two clinics rather than a mislabelled column.
UNIT_SWAP_COLUMN_SHARE = 0.9
UNIT_SWAP_MIN_READINGS = 10

# The analytical limits A4D's medical advisor gave, at the permissive end of
# each range he stated (mg/dL ~2-5 to ~720-800; mmol/L ~0.1-0.3 to ~40-45), so
# only a reading no machine could have produced is rejected. He separately
# confirmed that above 100 mmol/L is outright impossible.
MG_ANALYTICAL_MIN = 2.0
MG_ANALYTICAL_MAX = 800.0
MMOL_ANALYTICAL_MIN = 0.1
MMOL_ANALYTICAL_MAX = 45.0

GLUCOSE_COLUMN_PAIRS: list[tuple[str, str]] = [
    ("fbg_baseline_mg", "fbg_baseline_mmol"),
    ("fbg_updated_mg", "fbg_updated_mmol"),
]

# Zero is below the analytical floor of both units (~2-5 mg/dL, ~0.1-0.3
# mmol/L), so it cannot be a measurement. All 244 baseline mmol/L readings under
# 3 mmol/L in the tracker set are exactly 0 -- a placeholder for "not measured",
# which the advisor did not contest.
GLUCOSE_COLUMNS: list[str] = [col for pair in GLUCOSE_COLUMN_PAIRS for col in pair]


def column_is_recorded_in_mmol(values: pl.Series) -> bool:
    """Is this mg/dL-labelled column actually holding mmol/L readings?

    True only when the column has enough readings to judge and nearly all of
    them fall below the mmol/mg boundary. Nulls are not readings.
    """
    readings = values.drop_nulls()
    if len(readings) < UNIT_SWAP_MIN_READINGS:
        return False
    below = int((readings < MMOL_MG_BOUNDARY).sum())
    return below / len(readings) >= UNIT_SWAP_COLUMN_SHARE


def _blank_zero_readings(df: pl.DataFrame) -> pl.DataFrame:
    present = [col for col in GLUCOSE_COLUMNS if col in df.columns]
    if not present:
        return df
    return df.with_columns(
        [pl.when(pl.col(col) == 0).then(None).otherwise(pl.col(col)).alias(col) for col in present]
    )


def _swap_column_to_mmol(df: pl.DataFrame, mg_col: str, mmol_col: str) -> pl.DataFrame:
    """Move a wholly mmol-recorded column into its mmol sibling and rescale."""
    recorded = pl.col(mg_col)
    df = df.with_columns(
        # An mmol reading already present was recorded under a correctly
        # labelled header, so it wins over the one being recovered.
        pl.when(pl.col(mmol_col).is_null())
        .then(recorded)
        .otherwise(pl.col(mmol_col))
        .alias(mmol_col),
        (recorded * MMOL_TO_MG_FACTOR).alias(mg_col),
    )

    # The defect is the column's label, so the correction the source workbook
    # needs is file-level; a row-level record here would be the same finding
    # repeated hundreds of times.
    readings = int(df[mmol_col].drop_nulls().len())
    report_finding(
        patient_id="all",
        column=mg_col,
        original_value=None,
        message=(
            f"Column is labelled mg/dL but {UNIT_SWAP_COLUMN_SHARE:.0%}+ of its "
            f"{readings} readings are in mmol/L range; values moved to {mmol_col} "
            f"and rescaled by {MMOL_TO_MG_FACTOR:g}. Correct the header in the source workbook."
        ),
        error_code="glucose_unit_swapped",
        function_name="_swap_column_to_mmol",
    )
    return df


def _flag_suspect_readings(df: pl.DataFrame, mg_col: str) -> None:
    suspect = df.filter(pl.col(mg_col).is_not_null() & (pl.col(mg_col) < MMOL_MG_BOUNDARY))
    for row in suspect.iter_rows(named=True):
        report_finding(
            patient_id=row.get("patient_id") or "unknown",
            column=mg_col,
            original_value=row[mg_col],
            message=(
                f"Reading {row[mg_col]} in an mg/dL column is below "
                f"{MMOL_MG_BOUNDARY:g} mg/dL, where a mmol/L value lands. Kept as "
                "recorded -- a severe hypoglycaemic reading looks the same. "
                "Confirm the unit in the source workbook."
            ),
            error_code="glucose_unit_suspect",
            function_name="resolve_glucose_units",
        )


def resolve_glucose_units(df: pl.DataFrame) -> pl.DataFrame:
    """Correct whole columns recorded in the wrong unit; flag stray readings.

    Runs before range validation so the analytical limits are applied to
    corrected values, and before the mg/mmol cross-derivation so that step sees
    a column whose unit matches its name.
    """
    df = _blank_zero_readings(df)

    for mg_col, mmol_col in GLUCOSE_COLUMN_PAIRS:
        if mg_col not in df.columns or mmol_col not in df.columns:
            continue
        if column_is_recorded_in_mmol(df[mg_col]):
            df = _swap_column_to_mmol(df, mg_col, mmol_col)
        else:
            _flag_suspect_readings(df, mg_col)

    return df
