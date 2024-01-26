#' @title Create CSV with longitudinal patient data for a single variable.
#'
#' @description
#' Read in all cleaned patient data CSV and create a single data.frame.
#' Group this data by id and take only the months when there is a change in the medical data.
#'
#'
#' @param all_patient_data list of data frames with cleaned patient data from step 2.
#' @param output_folder root directory of the output folder.
#' @param variable name of the column that should be exported.
#' @param name name used to create the export file name.
create_table_longitudinal_data <-
    function(all_patient_data,
             output_folder,
             variable,
             name) {
        dynamic_patient_columns <-
            c(
                "blood_pressure_dias_mmhg",
                "blood_pressure_sys_mmhg",
                "bmi",
                "bmi_date",
                "clinic_code",
                "country_code",
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
                "id",
                "insulin_regimen",
                "last_clinic_visit_date",
                "last_remote_followup_date",
                "observations",
                "observations_category",
                "sheet_name",
                "status",
                "support_from_a4d",
                "testing_frequency",
                "tracker_date",
                "tracker_month",
                "tracker_year",
                "updated_2022_date",
                "weight"
            )

        patient_data <- all_patient_data %>%
            dplyr::bind_rows() %>%
            dplyr::select(tidyselect::all_of(dynamic_patient_columns))

        # get latest static patient data overall
        variable_lag <- paste0(variable, "_lag")
        longitudinal_data <- patient_data %>%
            tidyr::drop_na(!!variable) %>%
            dplyr::filter(get(variable) != ERROR_VAL_NUMERIC) %>%
            dplyr::group_by(id) %>%
            dplyr::arrange(tracker_year, tracker_month) %>%
            dplyr::filter(
                get(variable) != tidyr::replace_na(
                    dplyr::lag(get(variable), default = NULL),
                    ERROR_VAL_NUMERIC
                )
            ) %>%
            dplyr::ungroup() %>%
            dplyr::arrange(id, tracker_year, tracker_month)

        export_data_as_parquet(
            data = longitudinal_data,
            filename = paste0("longitudinal_data_", name),
            output_folder = output_folder,
            suffix = ""
        )
    }
