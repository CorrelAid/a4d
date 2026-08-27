"""Create final patient data tables from cleaned data."""

from pathlib import Path

import polars as pl
from loguru import logger


def read_cleaned_patient_data(cleaned_files: list[Path]) -> pl.DataFrame:
    """Read and combine all cleaned patient data files.

    Args:
        cleaned_files: List of paths to cleaned parquet files

    Returns:
        Combined DataFrame with all cleaned patient data
    """
    if not cleaned_files:
        raise ValueError("No cleaned files provided")

    dfs = [pl.read_parquet(file) for file in cleaned_files]
    return pl.concat(dfs, how="vertical")


def create_table_patient_data_static(patient_data: pl.DataFrame, output_dir: Path) -> Path:
    """Create static patient data table.

    Selects static columns (data that doesn't change monthly) from the already-loaded
    cleaned patient dataframe. Groups by patient_id and takes the latest available
    data (latest year and month).

    Args:
        patient_data: Combined cleaned patient dataframe (from read_cleaned_patient_data)
        output_dir: Directory to save output parquet file

    Returns:
        Path to created parquet file
    """
    static_columns = [
        "clinic_id",
        "dob",
        "fbg_baseline_mg",
        "fbg_baseline_mmol",
        "file_name",
        "hba1c_baseline",
        "hba1c_baseline_exceeds",
        "lost_date",
        "name",
        "patient_consent",
        "patient_id",
        "province",
        "recruitment_date",
        "sex",
        "status_out",
        "t1d_diagnosis_age",
        "t1d_diagnosis_date",
        "t1d_diagnosis_with_dka",
        "tracker_date",
        "tracker_month",
        "tracker_year",
    ]

    static_data = (
        patient_data.select(static_columns)
        .sort(["patient_id", "tracker_year", "tracker_month"])
        .group_by("patient_id")
        .last()
        .sort(["tracker_year", "tracker_month", "patient_id"])
    )

    logger.info(f"Static patient data dimensions: {static_data.shape}")

    output_file = output_dir / "patient_data_static.parquet"
    output_dir.mkdir(parents=True, exist_ok=True)
    static_data.write_parquet(output_file)

    return output_file


def create_table_patient_data_monthly(patient_data: pl.DataFrame, output_dir: Path) -> Path:
    """Create monthly patient data table.

    Selects dynamic monthly columns from the already-loaded cleaned patient
    dataframe. Keeps all monthly records.

    Args:
        patient_data: Combined cleaned patient dataframe (from read_cleaned_patient_data)
        output_dir: Directory to save output parquet file

    Returns:
        Path to created parquet file
    """
    monthly_columns = [
        "age",
        "bmi",
        "bmi_date",
        "clinic_id",
        "complication_screening",
        "complication_screening_results",
        "fbg_updated_date",
        "fbg_updated_mg",
        "fbg_updated_mmol",
        "file_name",
        "hba1c_updated",
        "hba1c_updated_exceeds",
        "hba1c_updated_date",
        "height",
        "hospitalisation_cause",
        "hospitalisation_date",
        "insulin_injections",
        "insulin_regimen",
        "insulin_total_units",
        "insulin_type",
        "insulin_subtype",
        "last_clinic_visit_date",
        "last_remote_followup_date",
        "observations",
        "observations_category",
        "patient_id",
        "sheet_name",
        "status",
        "support_level",
        "testing_frequency",
        "tracker_date",
        "tracker_month",
        "tracker_year",
        "weight",
    ]

    monthly_data = patient_data.select(monthly_columns).sort(
        ["tracker_year", "tracker_month", "patient_id"]
    )

    logger.info(f"Monthly patient data dimensions: {monthly_data.shape}")

    output_file = output_dir / "patient_data_monthly.parquet"
    output_dir.mkdir(parents=True, exist_ok=True)
    monthly_data.write_parquet(output_file)

    return output_file


def create_table_patient_data_annual(patient_data: pl.DataFrame, output_dir: Path) -> Path:
    """Create annual patient data table.

    Selects annual columns (data collected once per year) from the already-loaded
    cleaned patient dataframe. Groups by patient_id and tracker_year, taking the
    latest month for each year. Only includes data from 2024 onwards.

    Args:
        patient_data: Combined cleaned patient dataframe (from read_cleaned_patient_data)
        output_dir: Directory to save output parquet file

    Returns:
        Path to created parquet file
    """
    annual_columns = [
        "patient_id",
        "status",
        "edu_occ",
        "edu_occ_updated",
        "blood_pressure_updated",
        "blood_pressure_sys_mmhg",
        "blood_pressure_dias_mmhg",
        "complication_screening_kidney_test_date",
        "complication_screening_kidney_test_value",
        "complication_screening_eye_exam_date",
        "complication_screening_eye_exam_value",
        "complication_screening_foot_exam_date",
        "complication_screening_foot_exam_value",
        "complication_screening_lipid_profile_date",
        "complication_screening_lipid_profile_triglycerides_value",
        "complication_screening_lipid_profile_cholesterol_value",
        "complication_screening_lipid_profile_ldl_mg_value",
        "complication_screening_lipid_profile_ldl_mmol_value",
        "complication_screening_lipid_profile_hdl_mg_value",
        "complication_screening_lipid_profile_hdl_mmol_value",
        "complication_screening_thyroid_test_date",
        "complication_screening_thyroid_test_ft4_ng_value",
        "complication_screening_thyroid_test_ft4_pmol_value",
        "complication_screening_thyroid_test_tsh_value",
        "complication_screening_remarks",
        "dm_complication_eye",
        "dm_complication_kidney",
        "dm_complication_others",
        "dm_complication_remarks",
        "family_history",
        "other_issues",
        "tracker_date",
        "tracker_month",
        "tracker_year",
    ]

    annual_data = (
        patient_data.select(annual_columns)
        .filter(pl.col("tracker_year") >= 2024)
        .sort(["patient_id", "tracker_year", "tracker_month"])
        .group_by(["patient_id", "tracker_year"])
        .last()
        .sort(["tracker_year", "tracker_month", "patient_id"])
    )

    logger.info(f"Annual patient data dimensions: {annual_data.shape}")

    output_file = output_dir / "patient_data_annual.parquet"
    output_dir.mkdir(parents=True, exist_ok=True)
    annual_data.write_parquet(output_file)

    return output_file
