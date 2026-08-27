"""Tests for patient table creation."""

from pathlib import Path

import polars as pl
import pytest

from a4d.tables.patient import (
    create_table_patient_data_annual,
    create_table_patient_data_monthly,
    create_table_patient_data_static,
    read_cleaned_patient_data,
)


@pytest.fixture
def cleaned_patient_data_files(tmp_path: Path) -> list[Path]:
    """Create test cleaned patient data files."""
    data_dir = tmp_path / "cleaned"
    data_dir.mkdir()

    file1 = data_dir / "tracker1_2024_01.parquet"
    df1 = pl.DataFrame(
        {
            "patient_id": ["P001", "P002", "P003"],
            "clinic_id": ["C001", "C001", "C002"],
            "name": ["Alice", "Bob", "Charlie"],
            "dob": ["2010-01-15", "2011-03-20", "2009-08-10"],
            "sex": ["F", "M", "M"],
            "recruitment_date": ["2024-01-10", "2024-01-15", "2024-01-05"],
            "province": ["Province1", "Province1", "Province2"],
            "hba1c_baseline": [8.5, 7.2, 9.1],
            "hba1c_baseline_exceeds": [True, False, True],
            "fbg_baseline_mg": [120, 110, 130],
            "fbg_baseline_mmol": [6.7, 6.1, 7.2],
            "patient_consent": [True, True, True],
            "t1d_diagnosis_date": ["2023-01-01", "2022-05-10", "2021-12-15"],
            "t1d_diagnosis_age": [13, 11, 12],
            "t1d_diagnosis_with_dka": [True, False, True],
            "status_out": ["Active", "Active", "Active"],
            "lost_date": [None, None, None],
            "file_name": ["tracker1.xlsx", "tracker1.xlsx", "tracker1.xlsx"],
            "tracker_date": ["2024-01-31", "2024-01-31", "2024-01-31"],
            "tracker_month": [1, 1, 1],
            "tracker_year": [2024, 2024, 2024],
            "sheet_name": ["Jan 2024", "Jan 2024", "Jan 2024"],
            "weight": [45.5, 52.3, 48.1],
            "height": [155, 162, 158],
            "bmi": [18.9, 19.9, 19.3],
            "bmi_date": ["2024-01-15", "2024-01-18", "2024-01-20"],
            "age": [14, 13, 15],
            "status": ["Active", "Active", "Active"],
            "hba1c_updated": [7.8, 6.9, 8.5],
            "hba1c_updated_date": ["2024-01-20", "2024-01-22", "2024-01-18"],
            "hba1c_updated_exceeds": [False, False, True],
            "fbg_updated_mg": [115, 105, 125],
            "fbg_updated_mmol": [6.4, 5.8, 6.9],
            "fbg_updated_date": ["2024-01-20", "2024-01-22", "2024-01-18"],
            "insulin_type": ["Rapid", "Mixed", "Rapid"],
            "insulin_subtype": ["Lispro", "30/70", "Aspart"],
            "insulin_regimen": ["Basal-bolus", "Twice daily", "Basal-bolus"],
            "insulin_injections": [4, 2, 4],
            "insulin_total_units": [35, 28, 40],
            "testing_frequency": [4, 3, 4],
            "support_level": ["Full", "Full", "Partial"],
            "last_clinic_visit_date": ["2024-01-25", "2024-01-28", "2024-01-22"],
            "last_remote_followup_date": [None, None, None],
            "hospitalisation_date": [None, None, None],
            "hospitalisation_cause": [None, None, None],
            "observations": ["Doing well", "Good progress", "Needs improvement"],
            "observations_category": ["Good", "Good", "Fair"],
            "complication_screening": ["Kidney,Eye,Foot", "Kidney", None],
            "complication_screening_results": ["Normal", "Abnormal", None],
            "edu_occ": ["Student", "Student", "Student"],
            "edu_occ_updated": ["Student", "Student", "Student"],
            "blood_pressure_updated": ["110/70", "115/75", "120/80"],
            "blood_pressure_sys_mmhg": [110, 115, 120],
            "blood_pressure_dias_mmhg": [70, 75, 80],
            "complication_screening_kidney_test_date": ["2024-01-10", None, "2024-01-08"],
            "complication_screening_kidney_test_value": ["Normal", None, "Normal"],
            "complication_screening_eye_exam_date": ["2024-01-10", None, None],
            "complication_screening_eye_exam_value": ["Normal", None, None],
            "complication_screening_foot_exam_date": [None, None, None],
            "complication_screening_foot_exam_value": [None, None, None],
            "complication_screening_lipid_profile_date": [None, None, None],
            "complication_screening_lipid_profile_triglycerides_value": [None, None, None],
            "complication_screening_lipid_profile_cholesterol_value": [None, None, None],
            "complication_screening_lipid_profile_ldl_mg_value": [None, None, None],
            "complication_screening_lipid_profile_ldl_mmol_value": [None, None, None],
            "complication_screening_lipid_profile_hdl_mg_value": [None, None, None],
            "complication_screening_lipid_profile_hdl_mmol_value": [None, None, None],
            "complication_screening_thyroid_test_date": [None, None, None],
            "complication_screening_thyroid_test_ft4_ng_value": [None, None, None],
            "complication_screening_thyroid_test_ft4_pmol_value": [None, None, None],
            "complication_screening_thyroid_test_tsh_value": [None, None, None],
            "complication_screening_remarks": [None, None, None],
            "dm_complication_eye": [None, None, None],
            "dm_complication_kidney": [None, None, None],
            "dm_complication_others": [None, None, None],
            "dm_complication_remarks": [None, None, None],
            "family_history": ["No diabetes", "Type 2 in family", "No diabetes"],
            "other_issues": [None, None, None],
        }
    )
    df1.write_parquet(file1)

    file2 = data_dir / "tracker1_2024_02.parquet"
    df2 = pl.DataFrame(
        {
            "patient_id": ["P001", "P002"],
            "clinic_id": ["C001", "C001"],
            "name": ["Alice", "Bob"],
            "dob": ["2010-01-15", "2011-03-20"],
            "sex": ["F", "M"],
            "recruitment_date": ["2024-01-10", "2024-01-15"],
            "province": ["Province1", "Province1"],
            "hba1c_baseline": [8.5, 7.2],
            "hba1c_baseline_exceeds": [True, False],
            "fbg_baseline_mg": [120, 110],
            "fbg_baseline_mmol": [6.7, 6.1],
            "patient_consent": [True, True],
            "t1d_diagnosis_date": ["2023-01-01", "2022-05-10"],
            "t1d_diagnosis_age": [13, 11],
            "t1d_diagnosis_with_dka": [True, False],
            "status_out": ["Active", "Active"],
            "lost_date": [None, None],
            "file_name": ["tracker1.xlsx", "tracker1.xlsx"],
            "tracker_date": ["2024-02-29", "2024-02-29"],
            "tracker_month": [2, 2],
            "tracker_year": [2024, 2024],
            "sheet_name": ["Feb 2024", "Feb 2024"],
            "weight": [46.0, 52.8],
            "height": [155, 162],
            "bmi": [19.1, 20.1],
            "bmi_date": ["2024-02-15", "2024-02-18"],
            "age": [14, 13],
            "status": ["Active", "Active"],
            "hba1c_updated": [7.5, 6.7],
            "hba1c_updated_date": ["2024-02-20", "2024-02-22"],
            "hba1c_updated_exceeds": [False, False],
            "fbg_updated_mg": [110, 100],
            "fbg_updated_mmol": [6.1, 5.6],
            "fbg_updated_date": ["2024-02-20", "2024-02-22"],
            "insulin_type": ["Rapid", "Mixed"],
            "insulin_subtype": ["Lispro", "30/70"],
            "insulin_regimen": ["Basal-bolus", "Twice daily"],
            "insulin_injections": [4, 2],
            "insulin_total_units": [36, 29],
            "testing_frequency": [4, 3],
            "support_level": ["Full", "Full"],
            "last_clinic_visit_date": ["2024-02-25", "2024-02-28"],
            "last_remote_followup_date": [None, None],
            "hospitalisation_date": [None, None],
            "hospitalisation_cause": [None, None],
            "observations": ["Excellent progress", "Very good"],
            "observations_category": ["Excellent", "Good"],
            "complication_screening": ["Lipids,TSH", None],
            "complication_screening_results": ["Normal", None],
            "edu_occ": ["Student", "Student"],
            "edu_occ_updated": ["Student", "Student"],
            "blood_pressure_updated": ["108/68", "112/72"],
            "blood_pressure_sys_mmhg": [108, 112],
            "blood_pressure_dias_mmhg": [68, 72],
            "complication_screening_kidney_test_date": [None, None],
            "complication_screening_kidney_test_value": [None, None],
            "complication_screening_eye_exam_date": [None, None],
            "complication_screening_eye_exam_value": [None, None],
            "complication_screening_foot_exam_date": [None, None],
            "complication_screening_foot_exam_value": [None, None],
            "complication_screening_lipid_profile_date": [None, None],
            "complication_screening_lipid_profile_triglycerides_value": [None, None],
            "complication_screening_lipid_profile_cholesterol_value": [None, None],
            "complication_screening_lipid_profile_ldl_mg_value": [None, None],
            "complication_screening_lipid_profile_ldl_mmol_value": [None, None],
            "complication_screening_lipid_profile_hdl_mg_value": [None, None],
            "complication_screening_lipid_profile_hdl_mmol_value": [None, None],
            "complication_screening_thyroid_test_date": [None, None],
            "complication_screening_thyroid_test_ft4_ng_value": [None, None],
            "complication_screening_thyroid_test_ft4_pmol_value": [None, None],
            "complication_screening_thyroid_test_tsh_value": [None, None],
            "complication_screening_remarks": [None, None],
            "dm_complication_eye": [None, None],
            "dm_complication_kidney": [None, None],
            "dm_complication_others": [None, None],
            "dm_complication_remarks": [None, None],
            "family_history": ["No diabetes", "Type 2 in family"],
            "other_issues": [None, None],
        }
    )
    df2.write_parquet(file2)

    return [file1, file2]


def test_read_cleaned_patient_data(cleaned_patient_data_files: list[Path]):
    """Test reading and combining cleaned patient data files."""
    result = read_cleaned_patient_data(cleaned_patient_data_files)

    assert isinstance(result, pl.DataFrame)
    assert result.shape[0] == 5  # 3 rows from file1 + 2 rows from file2
    assert "patient_id" in result.columns
    assert "clinic_id" in result.columns
    assert set(result["patient_id"].to_list()) == {"P001", "P002", "P003"}


def test_read_cleaned_patient_data_empty_list():
    """Test that empty file list raises error."""
    with pytest.raises(ValueError, match="No cleaned files provided"):
        read_cleaned_patient_data([])


def test_create_table_patient_data_static(cleaned_patient_data_files: list[Path], tmp_path: Path):
    """Test creation of static patient data table."""
    output_dir = tmp_path / "output"

    patient_data = read_cleaned_patient_data(cleaned_patient_data_files)
    output_file = create_table_patient_data_static(patient_data, output_dir)

    assert output_file.exists()
    assert output_file.name == "patient_data_static.parquet"

    result = pl.read_parquet(output_file)

    assert result.shape[0] == 3
    assert set(result["patient_id"].to_list()) == {"P001", "P002", "P003"}

    p001_data = result.filter(pl.col("patient_id") == "P001")
    assert p001_data["tracker_month"][0] == 2
    assert p001_data["tracker_year"][0] == 2024

    p002_data = result.filter(pl.col("patient_id") == "P002")
    assert p002_data["tracker_month"][0] == 2
    assert p002_data["tracker_year"][0] == 2024

    p003_data = result.filter(pl.col("patient_id") == "P003")
    assert p003_data["tracker_month"][0] == 1
    assert p003_data["tracker_year"][0] == 2024

    assert "name" in result.columns
    assert "dob" in result.columns
    assert "recruitment_date" in result.columns
    assert "weight" not in result.columns
    assert "status" not in result.columns


def test_create_table_patient_data_monthly(cleaned_patient_data_files: list[Path], tmp_path: Path):
    """Test creation of monthly patient data table."""
    output_dir = tmp_path / "output"

    patient_data = read_cleaned_patient_data(cleaned_patient_data_files)
    output_file = create_table_patient_data_monthly(patient_data, output_dir)

    assert output_file.exists()
    assert output_file.name == "patient_data_monthly.parquet"

    result = pl.read_parquet(output_file)

    assert result.shape[0] == 5

    assert "weight" in result.columns
    assert "bmi" in result.columns
    assert "status" in result.columns
    assert "insulin_type" in result.columns
    assert "name" not in result.columns
    assert "dob" not in result.columns

    # Which screenings a clinic did this month, and what they found. Recorded
    # in every template since 2021 and published for the first time by ticket
    # 75 -- 4,031 selections and 3,349 outcomes across the corpus reached no
    # table before it.
    assert "complication_screening" in result.columns
    assert "complication_screening_results" in result.columns
    assert "Kidney,Eye,Foot" in result["complication_screening"].to_list()

    sorted_check = result["tracker_year"].to_list()
    assert sorted_check == sorted(sorted_check)


def test_create_table_patient_data_annual(cleaned_patient_data_files: list[Path], tmp_path: Path):
    """Test creation of annual patient data table."""
    output_dir = tmp_path / "output"

    patient_data = read_cleaned_patient_data(cleaned_patient_data_files)
    output_file = create_table_patient_data_annual(patient_data, output_dir)

    assert output_file.exists()
    assert output_file.name == "patient_data_annual.parquet"

    result = pl.read_parquet(output_file)

    assert result.shape[0] == 3

    assert "complication_screening_kidney_test_date" in result.columns
    assert "dm_complication_eye" in result.columns
    assert "family_history" in result.columns
    assert "name" not in result.columns
    assert "weight" not in result.columns

    p001_data = result.filter(pl.col("patient_id") == "P001")
    assert p001_data.shape[0] == 1
    assert p001_data["tracker_month"][0] == 2
    assert p001_data["tracker_year"][0] == 2024


def test_create_table_patient_data_annual_filters_pre_2024(tmp_path: Path):
    """Test that annual table filters out data before 2024."""
    data_dir = tmp_path / "cleaned"
    data_dir.mkdir()

    file1 = data_dir / "tracker_2023.parquet"
    df1 = pl.DataFrame(
        {
            "patient_id": ["P001"],
            "status": ["Active"],
            "tracker_month": [12],
            "tracker_year": [2023],
            "tracker_date": ["2023-12-31"],
            "edu_occ": ["Student"],
            "edu_occ_updated": ["Student"],
            "blood_pressure_updated": ["110/70"],
            "blood_pressure_sys_mmhg": [110],
            "blood_pressure_dias_mmhg": [70],
            "complication_screening_kidney_test_date": [None],
            "complication_screening_kidney_test_value": [None],
            "complication_screening_eye_exam_date": [None],
            "complication_screening_eye_exam_value": [None],
            "complication_screening_foot_exam_date": [None],
            "complication_screening_foot_exam_value": [None],
            "complication_screening_lipid_profile_date": [None],
            "complication_screening_lipid_profile_triglycerides_value": [None],
            "complication_screening_lipid_profile_cholesterol_value": [None],
            "complication_screening_lipid_profile_ldl_mg_value": [None],
            "complication_screening_lipid_profile_ldl_mmol_value": [None],
            "complication_screening_lipid_profile_hdl_mg_value": [None],
            "complication_screening_lipid_profile_hdl_mmol_value": [None],
            "complication_screening_thyroid_test_date": [None],
            "complication_screening_thyroid_test_ft4_ng_value": [None],
            "complication_screening_thyroid_test_ft4_pmol_value": [None],
            "complication_screening_thyroid_test_tsh_value": [None],
            "complication_screening_remarks": [None],
            "dm_complication_eye": [None],
            "dm_complication_kidney": [None],
            "dm_complication_others": [None],
            "dm_complication_remarks": [None],
            "family_history": ["No diabetes"],
            "other_issues": [None],
        }
    )
    df1.write_parquet(file1)

    output_dir = tmp_path / "output"
    patient_data = read_cleaned_patient_data([file1])
    output_file = create_table_patient_data_annual(patient_data, output_dir)

    result = pl.read_parquet(output_file)
    assert result.shape[0] == 0


def test_static_table_sorting(cleaned_patient_data_files: list[Path], tmp_path: Path):
    """Test that static table is sorted correctly."""
    output_dir = tmp_path / "output"
    patient_data = read_cleaned_patient_data(cleaned_patient_data_files)
    output_file = create_table_patient_data_static(patient_data, output_dir)

    result = pl.read_parquet(output_file)

    tracker_years = result["tracker_year"].to_list()
    tracker_months = result["tracker_month"].to_list()
    patient_ids = result["patient_id"].to_list()

    for i in range(len(result) - 1):
        if tracker_years[i] < tracker_years[i + 1]:
            continue
        elif tracker_years[i] == tracker_years[i + 1]:
            if tracker_months[i] < tracker_months[i + 1]:
                continue
            elif tracker_months[i] == tracker_months[i + 1]:
                assert patient_ids[i] <= patient_ids[i + 1]
