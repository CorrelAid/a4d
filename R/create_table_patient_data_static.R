#' @title Create CSV with static patient data
#'
#' @description
#' Read in all cleaned patient data CSV and create a single data.frame.
#' Group this data by id and take the latest available data (latest year and month).
#'
#'
#' @param all_patient_data list of data frames with cleaned patient data from step 2.
#' @param output_folder output directory.
create_table_patient_data_static <- function(all_patient_data, output_folder) {
    # THERE MIGHT BE STATIC COLUMNS MISSING - PLEASE ADD THEM
    static_patient_columns <-
        c(
            "age",
            "dob",
            "edu_occ",
            "fbg_baseline_mg",
            "fbg_baseline_mmol",
            "hba1c_baseline",
            "hba1c_baseline_exceeds",
            "id",
            "last_clinic_visit_date",
            "lost_date",
            "name",
            "province",
            "recruitment_date",
            "sex",
            "status_out",
            "t1d_diagnosis_age",
            "t1d_diagnosis_date",
            "t1d_diagnosis_with_dka",
            "tracker_date",
            "tracker_month",
            "tracker_year"
        )

    static_patient_data <- all_patient_data %>%
        dplyr::bind_rows() %>%
        dplyr::select(tidyselect::all_of(static_patient_columns))

    # get latest static patient data overall
    static_patient_data <- static_patient_data %>%
        dplyr::group_by(id) %>%
        dplyr::slice_max(tracker_year, n = 1) %>%
        dplyr::slice_max(tracker_month, n = 1) %>%
        dplyr::slice_head(n = 1) %>%
        dplyr::ungroup() %>%
        dplyr::arrange(tracker_year, tracker_month, id)

    testit::assert(sum(duplicated(static_patient_data$id)) == 0)

    export_data_as_parquet(
        data = static_patient_data,
        filename = "patient_data_static",
        output_folder = output_folder,
        suffix = ""
    )
}
