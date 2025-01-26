#' @title Create CSV with monthly patient data
#'
#' @description
#' Read in all cleaned patient data CSV and create a single data.frame.
#' Only take dynamic columns.
#'
#'
#' @param patient_data_files list of CSV files with cleaned patient data from step 2.
#' @param input_root root directory of the input CSV files.
#' @param output_root root directory of the output folder.
create_table_patient_data_monthly <- function(patient_data_files, input_root, output_root) {
    # THERE MIGHT BE MONTHLY COLUMNS MISSING - PLEASE ADD THEM
    dynamic_patient_columns <-
        c(
            "bmi",
            "bmi_date",
            "clinic_id",
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
            "weight"
        )

    patient_data <- read_cleaned_patient_data(input_root, patient_data_files) %>%
        dplyr::select(tidyselect::all_of(dynamic_patient_columns)) %>%
        dplyr::arrange(tracker_year, tracker_month, patient_id)

    logInfo(
        log_to_json(
            message = "patient_data dim: {values['dim']}.",
            values = list(dim = dim(patient_data)),
            script = "script3",
            file = "create_table_patient_data.R",
            functionName = "create_table_patient_data_monthly"
        )
    )

    export_data_as_parquet(
        data = patient_data,
        filename = "patient_data_monthly",
        output_root = output_root,
        suffix = ""
    )
}
