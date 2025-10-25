"""Meta schema definition for patient data.

This module defines the complete target schema for the patient_data table.
All cleaned patient data will conform to this schema, with missing columns
filled with NULL values.

This mirrors the R pipeline's meta schema approach (script2_process_patient_data.R)
where a complete schema is defined upfront, and only columns that exist in the
raw data are processed - the rest are left empty.
"""

import polars as pl
from typing import Dict


def get_patient_data_schema() -> Dict[str, pl.DataType]:
    """Get the complete meta schema for patient data.

    This schema defines ALL columns that should exist in the final
    patient_data table, along with their target data types.

    Returns:
        Dictionary mapping column names to Polars data types

    Note:
        - Not all columns will exist in every tracker file
        - Missing columns will be filled with NULL
        - All columns in output will match this schema exactly
    """
    return {
        # Metadata columns (always present from extraction)
        "file_name": pl.String,
        "clinic_id": pl.String,
        "tracker_year": pl.String,
        "tracker_month": pl.String,
        "sheet_name": pl.String,
        "patient_id": pl.String,
        "tracker_date": pl.Date,

        # Patient demographics
        "name": pl.String,
        "age": pl.Int32,
        "dob": pl.Date,
        "sex": pl.String,
        "province": pl.String,
        "district": pl.String,
        "village": pl.String,

        # Patient status
        "status": pl.String,
        "status_in_date": pl.Date,
        "status_out_date": pl.Date,
        "patient_consent": pl.String,

        # Diagnosis
        "t1d_diagnosis_date": pl.Date,
        "t1d_diagnosis_age": pl.Int32,
        "t1d_diagnosis_with_dka": pl.String,

        # Physical measurements
        "height": pl.Float64,
        "weight": pl.Float64,
        "bmi": pl.Float64,
        "bmi_date": pl.Date,

        # Blood pressure
        "blood_pressure_sys_mmhg": pl.Int32,
        "blood_pressure_dias_mmhg": pl.Int32,
        "blood_pressure_updated": pl.Date,

        # HbA1c
        "hba1c_baseline": pl.Float64,
        "hba1c_baseline_exceeds": pl.Boolean,
        "hba1c_updated": pl.Float64,
        "hba1c_updated_exceeds": pl.Boolean,
        "hba1c_updated_date": pl.Date,

        # FBG (Fasting Blood Glucose)
        "fbg_baseline_mg": pl.Float64,
        "fbg_baseline_mmol": pl.Float64,
        "fbg_updated_mg": pl.Float64,
        "fbg_updated_mmol": pl.Float64,
        "fbg_updated_date": pl.Date,

        # Testing
        "testing_frequency": pl.Int32,

        # Insulin type and regimen
        "insulin_type": pl.String,
        "insulin_subtype": pl.String,
        "insulin_regimen": pl.String,
        "insulin_total_units": pl.Float64,

        # Human insulin (2024+ trackers)
        "human_insulin_pre_mixed": pl.String,
        "human_insulin_short_acting": pl.String,
        "human_insulin_intermediate_acting": pl.String,

        # Analog insulin (2024+ trackers)
        "analog_insulin_rapid_acting": pl.String,
        "analog_insulin_long_acting": pl.String,

        # Support
        "support_level": pl.String,
        "support_date": pl.Date,

        # Clinic visits
        "clinic_visit": pl.String,
        "remote_followup": pl.String,

        # Hospitalisation
        "hospitalisation": pl.String,
        "hospitalisation_cause": pl.String,
        "hospitalisation_date": pl.Date,

        # DM Complications
        "dm_complication_eye": pl.String,
        "dm_complication_kidney": pl.String,
        "dm_complication_others": pl.String,
        "dm_complications": pl.String,

        # Complication screening - Eye
        "complication_screening_eye_exam_date": pl.Date,
        "complication_screening_eye_exam_value": pl.String,

        # Complication screening - Foot
        "complication_screening_foot_exam_date": pl.Date,
        "complication_screening_foot_exam_value": pl.String,

        # Complication screening - Kidney
        "complication_screening_kidney_test_date": pl.Date,
        "complication_screening_kidney_test_value": pl.String,

        # Complication screening - Lipid profile
        "complication_screening_lipid_profile_date": pl.Date,
        "complication_screening_lipid_profile_cholesterol_value": pl.String,
        "complication_screening_lipid_profile_hdl_mmol_value": pl.Float64,
        "complication_screening_lipid_profile_hdl_mg_value": pl.Float64,
        "complication_screening_lipid_profile_ldl_mmol_value": pl.Float64,
        "complication_screening_lipid_profile_ldl_mg_value": pl.Float64,
        "complication_screening_lipid_profile_triglycerides_value": pl.Float64,

        # Observations
        "observations_category": pl.String,
        "observations": pl.String,
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

    Example:
        >>> schema = get_patient_data_schema()
        >>> df_clean = apply_schema(df_raw)
        >>> # Now df_clean has ALL schema columns, missing ones are NULL
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
        col for col, dtype in schema.items()
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
