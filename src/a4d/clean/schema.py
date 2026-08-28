"""Meta schema definition for patient data.

Every cleaned patient parquet conforms to this, whichever columns its source
tracker happened to carry -- so downstream consumers see one stable shape
across 254 trackers and nine template years.
"""

import polars as pl

# Columns the reference list recognises and extraction reads, which the fixed
# output shape below then drops. Each entry is a decision with its reason, not
# an oversight: the guard in tests/test_clean/test_schema.py fails the build
# when a recognised column joins or leaves this set unexplained.
#
# The gap this closes is real. `complication_screening` and
# `complication_screening_results` sat here unnoticed until 2026-08-28 -- read
# out of all 254 workbooks, dropped, and never mentioned in any report --
# because the reference list and this schema are two separate lists and nothing
# compared them.
#
# Years below are the last year any tracker in the 255-file corpus carries a
# value for that column, measured 2026-08-28. Every one of them predates 2024,
# which is why none is published: a column the current template no longer
# carries was a field A4D stopped collecting, not a field the pipeline loses.
UNPUBLISHED_COLUMNS: dict[str, str] = {
    "blood_pressure_mmhg": (
        "Consumed, not dropped: split into blood_pressure_sys_mmhg and "
        "blood_pressure_dias_mmhg before the schema is applied, so the source "
        "column has already done its job (19,273 values, 73 trackers)."
    ),
    "est_strips_pmoth": (
        "Retired template field -- estimated test strips per month, last "
        "recorded in 2019 (3,749 values, 22 trackers)."
    ),
    "insulin_dosage": (
        "Retired template field, last recorded in 2018 (2,533 values, 8 "
        "trackers). Superseded by insulin_total_units, which is published."
    ),
    "meter_received_date": (
        "Retired template field -- the date a glucose meter was handed over, "
        "last recorded in 2023 (1,788 values, 17 trackers)."
    ),
    "insulin_required_month": (
        "Retired template field -- estimated insulin required per month, last "
        "recorded in 2018 (1,780 values, 4 trackers)."
    ),
    "insulin_required_year": (
        "Retired template field -- estimated insulin required per year, last "
        "recorded in 2019 (486 values, 4 trackers)."
    ),
    "complication_screening_date": (
        "Retired template field, last recorded in 2022 (397 values, 19 "
        "trackers). The per-test screening dates the current template uses "
        "are published instead, one column per test."
    ),
    "family_support_scale": (
        "Retired template field, recorded in 2019 only (196 values, 8 trackers)."
    ),
    "dm_complications": (
        "Retired template field, recorded in 2023 only (164 values, 7 "
        "trackers). The current template records complications per organ, in "
        "the published dm_complication_* columns."
    ),
    "inactive_reason": (
        "Retired template field: no tracker in the corpus carries a value. "
        "The published status_out column records why a patient left."
    ),
    "insulin_required_product_name": (
        "Retired template field: no tracker in the corpus carries a value."
    ),
    "latest_complication_screenning": (
        "Retired template field (misspelling is the workbook's): no tracker "
        "in the corpus carries a value."
    ),
    "num_admin_hosp_dka": (
        "Retired template field -- the 2023 per-cause hospitalisation counts. "
        "No tracker in the corpus carries a value."
    ),
    "num_admin_hosp_hypo": (
        "Retired template field -- the 2023 per-cause hospitalisation counts. "
        "No tracker in the corpus carries a value."
    ),
    "num_admin_hosp_other": (
        "Retired template field -- the 2023 per-cause hospitalisation counts. "
        "No tracker in the corpus carries a value."
    ),
    "num_admin_hosp_other_reason": (
        "Retired template field -- the 2023 per-cause hospitalisation counts. "
        "No tracker in the corpus carries a value."
    ),
    "num_admin_hosp_total": (
        "Retired template field -- the 2023 per-cause hospitalisation counts. "
        "No tracker in the corpus carries a value. hospitalisation_date and "
        "hospitalisation_cause are published instead."
    ),
    "qol_survey": (
        "Retired template field -- quality-of-life survey. No tracker in the "
        "corpus carries a value."
    ),
    # Join artifacts. join_static_sheet suffixes a static sheet's column when
    # the month sheets already carry one of the same name, so the suffixed
    # copy is the one the join discards.
    "fbg_baseline_mg.static": (
        "The Patient List's own copy of a baseline reading the month sheets "
        "also carry. Ticket 29 decided the monthly copy wins: the two agree "
        "on 92.4% of ~10,000 rows and nothing establishes which sheet is "
        "authoritative on the rest (8,892 values, 21 trackers)."
    ),
    "fbg_baseline_mmol.static": (
        "The Patient List's own copy of a baseline reading the month sheets "
        "also carry, discarded by the same ticket 29 decision as the mg "
        "column above (1,061 values, 3 trackers)."
    ),
}


def get_patient_data_schema() -> dict[str, type[pl.DataType] | pl.DataType]:
    """Get the complete meta schema for patient data.

    Columns are in alphabetical order. The order is part of the contract:
    BigQuery consumers and the parquet snapshots both depend on it.

    Returns:
        Dictionary mapping column names to Polars data types
    """
    return {
        "age": pl.Int32,
        "analog_insulin_long_acting": pl.String,
        "analog_insulin_rapid_acting": pl.String,
        "blood_pressure_dias_mmhg": pl.Int32,
        "blood_pressure_sys_mmhg": pl.Int32,
        "blood_pressure_updated": pl.Date,
        "bmi": pl.Float64,
        "bmi_date": pl.Date,
        "clinic_id": pl.String,
        "clinic_visit": pl.String,
        "complication_screening": pl.String,
        "complication_screening_eye_exam_date": pl.Date,
        "complication_screening_eye_exam_value": pl.String,
        "complication_screening_foot_exam_date": pl.Date,
        "complication_screening_foot_exam_value": pl.String,
        "complication_screening_kidney_test_date": pl.Date,
        "complication_screening_kidney_test_value": pl.String,
        "complication_screening_lipid_profile_cholesterol_value": pl.String,
        "complication_screening_lipid_profile_date": pl.Date,
        "complication_screening_lipid_profile_hdl_mmol_value": pl.Float64,
        "complication_screening_lipid_profile_hdl_mg_value": pl.Float64,
        "complication_screening_lipid_profile_ldl_mmol_value": pl.Float64,
        "complication_screening_lipid_profile_ldl_mg_value": pl.Float64,
        "complication_screening_lipid_profile_triglycerides_value": pl.Float64,
        "complication_screening_remarks": pl.String,
        "complication_screening_results": pl.String,
        "complication_screening_thyroid_test_date": pl.Date,
        "complication_screening_thyroid_test_ft4_pmol_value": pl.Float64,
        "complication_screening_thyroid_test_ft4_ng_value": pl.Float64,
        "complication_screening_thyroid_test_tsh_value": pl.Float64,
        "dm_complication_eye": pl.String,
        "dm_complication_kidney": pl.String,
        "dm_complication_others": pl.String,
        "dm_complication_remarks": pl.String,
        "dob": pl.Date,
        "edu_occ": pl.String,
        "edu_occ_updated": pl.Date,
        "family_history": pl.String,
        "fbg_baseline_mg": pl.Float64,
        "fbg_baseline_mmol": pl.Float64,
        "fbg_updated_date": pl.Date,
        "fbg_updated_mg": pl.Float64,
        "fbg_updated_mmol": pl.Float64,
        "file_name": pl.String,
        "hba1c_baseline": pl.Float64,
        "hba1c_baseline_exceeds": pl.Boolean,
        "hba1c_updated": pl.Float64,
        "hba1c_updated_exceeds": pl.Boolean,
        "hba1c_updated_date": pl.Date,
        "height": pl.Float64,
        "hospitalisation_cause": pl.String,
        "hospitalisation_date": pl.Date,
        "human_insulin_intermediate_acting": pl.String,
        "human_insulin_pre_mixed": pl.String,
        "human_insulin_short_acting": pl.String,
        "insulin_injections": pl.Float64,
        "insulin_regimen": pl.String,
        "insulin_total_units": pl.Float64,
        "insulin_type": pl.String,
        "insulin_subtype": pl.String,
        "last_clinic_visit_date": pl.Date,
        "last_remote_followup_date": pl.Date,
        "lost_date": pl.Date,
        "name": pl.String,
        "observations": pl.String,
        "observations_category": pl.String,
        "other_issues": pl.String,
        "patient_consent": pl.String,
        "patient_id": pl.String,
        "province": pl.String,
        "recruitment_date": pl.Date,
        "remote_followup": pl.String,
        "sex": pl.String,
        "sheet_name": pl.String,
        "status": pl.String,
        "status_out": pl.String,
        "support_level": pl.String,
        "t1d_diagnosis_age": pl.Int32,
        "t1d_diagnosis_date": pl.Date,
        "t1d_diagnosis_with_dka": pl.String,
        "testing_frequency": pl.Int32,
        "tracker_date": pl.Date,
        "tracker_month": pl.Int32,
        "tracker_year": pl.Int32,
        "weight": pl.Float64,
    }


def apply_schema(df: pl.DataFrame) -> pl.DataFrame:
    """Apply the meta schema to a DataFrame.

    This function:
    1. Adds missing columns with NULL values typed per the schema.
    2. Reorders columns to match schema order.

    Casting is the caller's responsibility (see ``safe_convert_column``).

    Args:
        df: Input DataFrame (may be missing columns)

    Returns:
        DataFrame with complete schema applied
    """
    schema = get_patient_data_schema()

    # Start with existing columns
    df_result = df

    # Add missing columns with NULL values
    missing_cols = set(schema.keys()) - set(df.columns)
    for col in missing_cols:
        df_result = df_result.with_columns(pl.lit(None, dtype=schema[col]).alias(col))

    # Reorder columns to match schema order
    df_result = df_result.select(list(schema.keys()))

    return df_result


def get_numeric_columns() -> list[str]:
    """Get list of numeric columns from schema."""
    schema = get_patient_data_schema()
    return [
        col
        for col, dtype in schema.items()
        if dtype in (pl.Int32, pl.Int64, pl.Float32, pl.Float64)
    ]


def get_date_columns() -> list[str]:
    """Get list of date columns from schema."""
    schema = get_patient_data_schema()
    return [col for col, dtype in schema.items() if dtype == pl.Date]


def get_boolean_columns() -> list[str]:
    """Get list of boolean columns from schema."""
    schema = get_patient_data_schema()
    return [col for col, dtype in schema.items() if dtype == pl.Boolean]


def get_string_columns() -> list[str]:
    """Get list of string columns from schema."""
    schema = get_patient_data_schema()
    return [col for col, dtype in schema.items() if dtype == pl.String]
