#' @title Create clinic static data table
#'
#' @description
#' This function reads the clinic data from an Excel file, fills missing values, and exports the data as a parquet file.
#'
#' @param output_root The root directory of the output folder.
# @export
create_table_clinic_static_data <- function(output_root) {
    clinic_data <- readxl::read_excel(here::here("reference_data", "clinic_data.xlsx"))
    clinic_data <- clinic_data %>%
        tidyr::fill(country_code:clinic_id, .direction = "down")

    logInfo(
        log_to_json(
            message = "clinic_data dim: {values['dim']}.",
            values = list(dim = dim(clinic_data)),
            script = "script3",
            file = "create_table_clinic_static_data.R",
            functionName = "create_table_clinic_static_data"
        )
    )

    export_data_as_parquet(
        data = clinic_data,
        filename = "clinic_data_static",
        output_root = output_root,
        suffix = ""
    )
}
