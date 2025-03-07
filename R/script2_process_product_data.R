#' @title Process raw product data
#'
#' @description
#' This function reads the raw product data from a parquet file, cleans the data, and exports the cleaned data as a parquet file.
#'
#' @param paths list of paths to the input and output directories.
#' @param product_file name of the raw product data file.
#' @param product_file_name base name of the raw product data file.
#' @param synonyms_product list of synonyms for the product data.
#' @param output_root The root directory of the output folder.
#'
#' @export
process_raw_product_file <- function(paths, product_file, product_file_name, synonyms_product, output_root) {
    product_file_path <-
        file.path(paths$tracker_root, product_file)

    df_product_raw <- arrow::read_parquet(product_file_path)

    df_product_raw <- reading_product_data_step2(df_product_raw, synonyms_product)

    logDebug(
        log_to_json(
            message = "df_product_raw dim: {values['dim']}.",
            values = list(dim = dim(df_product_raw)),
            script = "script2",
            file = "script2_process_product_data.R",
            functionName = "process_raw_product_file"
        )
    )

    export_data_as_parquet(
        data = df_product_raw,
        filename = stringr::str_replace(product_file_name, "_product_raw", ""),
        output_root = output_root,
        suffix = "_product_cleaned"
    )
}
