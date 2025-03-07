options(readxl.show_progress = FALSE)

ERROR_VAL_NUMERIC <<- 999999
ERROR_VAL_CHARACTER <<- "Undefined"
ERROR_VAL_DATE <<- "9999-09-09"

main <- function() {
    paths <- init_paths(c("patient_data_cleaned", "product_data_cleaned"), delete = TRUE)
    setup_logger(paths$output_root, "script2")
    patient_data_files <- get_files(paths$output_root, pattern = "patient_raw.parquet$")
    product_data_files <- get_files(paths$tracker_root, pattern = "product_raw.parquet$")

    logInfo(
        log_to_json(
            "Found {values['len']} csv files with patient data under {values['root']}. ",
            values = list(len = length(patient_data_files), root = paths$output_root),
            script = "script2",
            file = "run_script2_clean_data.R",
            functionName = "main"
        )
    )
    logInfo(
        log_to_json(
            "Found {values['len']} csv files with product data under {values['root']}. ",
            values = list(len = length(product_data_files), root = paths$output_root),
            script = "script2",
            file = "run_script2_clean_data.R",
            functionName = "main"
        )
    )

    for (i in seq_along(patient_data_files)) {
        patient_file <- patient_data_files[i]
        patient_file_name <- tools::file_path_sans_ext(basename(patient_file))
        tictoc::tic(paste("Processing raw patient data:", patient_file_name))

        logfile <- paste0(patient_file_name)
        with_file_logger(logfile,
            {
                tryCatch(
                    process_raw_patient_file(paths, patient_file, patient_file_name, paths$patient_data_cleaned),
                    error = function(e) {
                        logError(
                            log_to_json(
                                "Could not process raw patient data. Error = {values['e']}.",
                                values = list(e = e$message),
                                script = "script2",
                                file = "script2_process_patient_data.R",
                                errorCode = "critical_abort",
                                functionName = "process_raw_patient_file"
                            )
                        )
                    },
                    warning = function(w) {
                        logWarn(
                            log_to_json(
                                "Could not process raw patient data. Warning = {values['w']}.",
                                values = list(w = w$message),
                                script = "script2",
                                file = "script2_process_patient_data.R",
                                warningCode = "critical_abort",
                                functionName = "process_raw_patient_file"
                            )
                        )
                    }
                )
            },
            output_root = paths$output_root
        )
        tictoc::toc()
        cat(paste("Processed ", i, " of ", length(patient_data_files), " (", round(i / length(patient_data_files) * 100, 0), "%) raw patient files.\n"))
    }

    synonyms <- get_synonyms()
    synonyms_product <- synonyms$product

    for (i in seq_along(product_data_files)) {
        product_file <- product_data_files[i]
        product_file_name <- tools::file_path_sans_ext(basename(product_file))
        tictoc::tic(paste("Processing product data:", product_file_name))

        logfile <- paste0(product_file_name)
        with_file_logger(logfile,
            {
                tryCatch(
                    process_raw_product_file(paths, product_file, product_file_name, synonyms_product, paths$product_data_cleaned),
                    error = function(e) {
                        logError(
                            log_to_json(
                                "Could not process raw product data. Error = {values['e']}.",
                                values = list(e = e$message),
                                script = "script2",
                                file = "script2_process_product_data.R",
                                functionName = "process_raw_product_file",
                                errorCode = "critical_abort"
                            )
                        )
                    },
                    warning = function(w) {
                        logWarn(
                            log_to_json(
                                "Could not process raw product data. Warning = {values['w']}.",
                                values = list(w = w$message),
                                script = "script2",
                                file = "script2_process_product_data.R",
                                functionName = "process_raw_product_file",
                                warningCode = "critical_abort"
                            )
                        )
                    }
                )
            },
            output_root = paths$output_root
        )
        tictoc::toc()
        cat(paste("Processed ", i, " of ", length(product_data_files), " (", round(i / length(product_data_files) * 100, 0), "%) product files.\n"))
    }
}

main()

clearLoggers()
