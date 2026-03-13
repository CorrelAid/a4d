#' Process tracker file.
#'
#' @param paths list of paths to directories.
#' @param tracker_file Name of the tracker file.
#' @param tracker_name Basename of the tracker file.
#' @param synonyms list of synonyms for patient and product data.
#'
#' @export
process_tracker_file <- function(paths, tracker_file, tracker_name, synonyms) {
    tracker_data_file <-
        file.path(paths$tracker_root, tracker_file)

    logInfo(
        log_to_json(
            "Current file: {values['file']}.",
            values = list(file = tracker_name),
            script = "script1",
            file = "script1_process_tracker_file.R",
            functionName = "process_tracker_file"
        )
    )

    logfile <- paste0(tracker_name, "_", "patient")
    with_file_logger(logfile,
        {
            tryCatch(
                process_tracker_patient_data(
                    tracker_name = tracker_name,
                    tracker_data_file = tracker_data_file,
                    output_root = paths$patient_data_raw,
                    synonyms_patient = synonyms$patient
                ),
                error = function(e) {
                    logError(
                        log_to_json(
                            "Could not process patient data. Error = {values['e']}.",
                            values = list(e = e$message),
                            script = "script1",
                            file = "script1_process_patient_data.R",
                            errorCode = "critical_abort",
                            functionName = "process_tracker_patient_data"
                        )
                    )
                },
                warning = function(w) {
                    logWarn(
                        log_to_json(
                            "Could not process patient data. Warning = {values['w']}.",
                            values = list(w = w$message),
                            script = "script1",
                            file = "script1_process_patient_data.R",
                            warningCode = "critical_abort",
                            functionName = "process_tracker_patient_data"
                        )
                    )
                }
            )
        },
        output_root = paths$output_root
    )

    logfile <- paste0(tracker_name, "_", "product")

    with_file_logger(logfile,
        {
            tryCatch(
                process_tracker_product_data(
                    tracker_name = tracker_name,
                    tracker_data_file = tracker_data_file,
                    output_root = paths$product_data_raw,
                    synonyms_product = synonyms$product
                ),
                error = function(e) {
                    logError(
                        log_to_json(
                            "Could not process product data. Error = {values['e']}.",
                            values = list(e = e$message),
                            script = "script1",
                            file = "script1_process_product_data.R",
                            errorCode = "critical_abort",
                            functionName = "process_tracker_product_data"
                        )
                    )
                },
                warning = function(w) {
                    logWarn(
                        log_to_json(
                            "Could not process product data. Warning = {values['w']}.",
                            values = list(w = w$message),
                            script = "script1",
                            file = "script1_process_product_data.R",
                            warningCode = "critical_abort",
                            functionName = "process_tracker_product_data"
                        )
                    )
                }
            )
        },
        output_root = paths$output_root
    )
}
