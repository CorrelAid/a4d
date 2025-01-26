#' @title Process tracker patient data
#'
#' @description
#' This function reads the patient data from a CSV file, adds a file name column,
#' and exports the data as a parquet file.
#'
#' @param tracker_name The name of the tracker.
#' @param tracker_data_file The path to the tracker data file.
#' @param output_root The root directory of the output folder.
#' @param synonyms_patient A named list of synonyms for the patient data columns.
#'
#' @export
process_tracker_patient_data <-
    function(tracker_name,
             tracker_data_file,
             output_root,
             synonyms_patient) {
        df_patient_raw <-
            reading_patient_data(
                tracker_data_file = tracker_data_file,
                columns_synonyms = synonyms_patient
            )

        df_patient_raw <- df_patient_raw %>% dplyr::mutate(file_name = tracker_name)

        # instead of clinic_code and country_code, we extract clinic_id from parent folder
        # and join with static clinic data later in the database
        df_patient_raw$clinic_id <- basename(dirname(tracker_data_file))

        logInfo(
            log_to_json(
                message = "df patient data dim: {values['dim']}.",
                values = list(dim = dim(df_patient_raw)),
                script = "script1",
                file = "script1_process_patient_data.R",
                functionName = "process_tracker_patient_data"
            )
        )

        export_data_as_parquet(
            data = df_patient_raw,
            filename = tracker_name,
            output_root = output_root,
            suffix = paste0("_patient_raw")
        )
    }
