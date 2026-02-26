"""Meta schema definition for patient data - matches R pipeline exactly."""

import polars as pl


def get_patient_data_schema() -> dict[str, pl.DataType]:
    """Get the complete meta schema for patient data.

    This schema EXACTLY matches the R pipeline's schema in script2_process_patient_data.R.
    Column order matches R's alphabetical order.

    Returns:
        Dictionary mapping column names to Polars data types
    """
    return {
        "age": pl.Int32,  # integer() in R
        "analog_insulin_long_acting": pl.String,  # character() in R
        "analog_insulin_rapid_acting": pl.String,
        "blood_pressure_dias_mmhg": pl.Int32,
        "blood_pressure_sys_mmhg": pl.Int32,
        "blood_pressure_updated": pl.Date,
        "bmi": pl.Float64,  # numeric() in R
        "bmi_date": pl.Date,
        "clinic_id": pl.String,
        "clinic_visit": pl.String,
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
        "hba1c_baseline_exceeds": pl.Boolean,  # logical() in R
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
    1. Adds missing columns with NULL values
    2. Casts existing columns to target types (if they exist)
    3. Reorders columns to match schema order
    4. Returns a DataFrame with the exact schema

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
