#' @title Process tracker product data
#'
#' @description
#' This function reads the product data from an Excel file,
#' fills missing values, and exports the data as a parquet file.
#'
#' @param tracker_name The name of the tracker.
#' @param tracker_data_file The path to the tracker data file.
#' @param output_root The root directory of the output folder.
#' @param synonyms_product A named list of synonyms for the product data columns.
#'
#' @export
process_tracker_product_data <-
    function(tracker_name,
             tracker_data_file,
             output_root,
             synonyms_product) {
        df_raw_product <-
            reading_product_data_step1(
                tracker_data_file = tracker_data_file,
                columns_synonyms = synonyms_product
            )

        if (!is.null(df_raw_product)) {
            df_raw_product <- df_raw_product %>% dplyr::mutate(file_name = tracker_name)

            df_raw_product$clinic_id <- basename(dirname(tracker_data_file))

            logInfo(
                log_to_json(
                    message = "df_raw_product dim: {values['dim']}.",
                    values = list(dim = dim(df_raw_product)),
                    script = "script1",
                    file = "script1_process_product_data.R",
                    functionName = "process_tracker_product_data"
                )
            )

            # product set sensitive column to NA and add tracker file name as a column
            export_data_as_parquet(
                data = df_raw_product,
                filename = tracker_name,
                output_root = output_root,
                suffix = "_product_raw"
            )
        } else {
            logWarn(
                log_to_json(
                    message = "Empty product data!",
                    script = "script1",
                    file = "script1_process_product_data.R",
                    functionName = "process_tracker_product_data",
                    warningCode = "empty_product_data"
                )
            )
        }
    }
