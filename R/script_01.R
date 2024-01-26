process_tracker_file <- function(tracker_file, tracker_name, tracker_root, output_folder, export = FALSE) {
    tracker_data_file <-
        file.path(tracker_root, tracker_file)
    synonyms <- get_synonyms()

    df_raw_patient <- extract_raw_patient_data(
        tracker_name = tracker_name,
        tracker_data_file = tracker_data_file,
        output_folder = output_folder,
        synonyms_patient = synonyms$patient,
        export
    )


    df_raw_product <- extract_raw_product_data(
        tracker_name = tracker_name,
        tracker_data_file = tracker_data_file,
        output_folder = paths$product_data_raw,
        synonyms_product = synonyms$product,
        export
    )

    list(patients = df_raw_patient, products = df_raw_product)
}


extract_raw_patient_data <-
    function(tracker_name,
             tracker_data_file,
             output_folder,
             synonyms_patient,
             export = FALSE) {
        df_raw_patient <-
            reading_patient_data(
                tracker_data_file = tracker_data_file,
                columns_synonyms = synonyms_patient
            )

        df_raw_patient <- df_raw_patient %>% dplyr::mutate(file_name = tracker_name)

        logDebug(
            "df_raw_patient dim: ",
            dim(df_raw_patient) %>% as.data.frame(),
            "."
        )

        if (export) {
            export_data_as_parquet(
                data = df_raw_patient,
                filename = tracker_name,
                output_folder = output_folder,
                suffix = "_patient_raw"
            )
        }

        df_raw_patient
    }


extract_raw_product_data <-
    function(tracker_name,
             tracker_data_file,
             output_folder,
             synonyms_product,
             export = FALSE) {
        df_raw_product <-
            reading_product_data_step1(
                tracker_data_file = tracker_data_file,
                columns_synonyms = synonyms_product
            )

        if (!is.null(df_raw_product)) {
            df_raw_product <- df_raw_product %>% dplyr::mutate(file_name = tracker_name)
        } else {
            logDebug("Empty product data")
        }

        logDebug(
            "df_raw_product dim: ",
            dim(df_raw_product) %>% as.data.frame(),
            "."
        )

        # product set sensitive column to NA and add tracker file name as a column
        if (!is.null(df_raw_product)) {
            if (export) {
                export_data_as_parquet(
                    data = df_raw_product,
                    filename = tracker_name,
                    output_folder = output_folder,
                    suffix = "_product_raw"
                )
            }
        } else {
            logWarn("No product data in the file")
        }

        df_raw_product
    }
