#' @title Create CSV with annual patient data
#'
#' @description
#' Read in all cleaned patient data CSV and create a single data.frame.
#' Group this data by id and take the latest available data (latest year and month).
#'
#'
#' @param patient_data_files list of CSV files with cleaned patient data from step 2.
#' @param input_root root directory of the input CSV files.
#' @param output_root root directory of the output folder.
create_table_patient_data_annual <- function(patient_data_files, input_root, output_root) {
    # THERE MIGHT BE STATIC COLUMNS MISSING - PLEASE ADD THEM
    annual_patient_columns <-
        c(
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
            "tracker_year"
        )


    annual_patient_data <- read_cleaned_patient_data(input_root, patient_data_files) %>%
        dplyr::select(tidyselect::all_of(annual_patient_columns))

    # get annual patient data for each year
    annual_patient_data <- annual_patient_data %>%
        dplyr::filter(tracker_year >= 2024) %>%
        dplyr::group_by(patient_id, tracker_year) %>%
        dplyr::slice_max(tracker_month, n = 1) %>% # Get the last month for each year
        dplyr::ungroup() %>%
        dplyr::arrange(tracker_year, tracker_month, patient_id)

    logInfo(
        log_to_json(
            message = "annual_patient_data dim: {values['dim']}.",
            values = list(dim = dim(annual_patient_data)),
            script = "script3",
            file = "script3_create_table_patient_data_annual.R",
            functionName = "create_table_patient_data_annual"
        )
    )

    export_data_as_parquet(
        data = annual_patient_data,
        filename = "patient_data",
        output_root = output_root,
        suffix = "_annual"
    )
}
