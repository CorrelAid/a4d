# current time
current_timestamp <- Sys.time()

main <- function() {
    config <- config::get()
    subdirs <- c(
        "patient_data_cleaned",
        "patient_data_raw",
        "product_data_cleaned",
        "product_data_raw"
    )
    paths <- init_paths(subdirs, delete = FALSE)

    tracker_files <- get_files(paths$tracker_root, pattern = "*.xlsx")

    all_data <- tibble::tibble()
    for (file in tracker_files) {
        row <- list()
        file_path <- file.path(paths$tracker_root, file)
        file_name <- tools::file_path_sans_ext(basename(file))
        row$file_name <- file_name
        clinic_code <- basename(dirname(file))
        row$clinic_code <- clinic_code
        row$md5 <- digest::digest(file_path, algo = "md5", serialize = FALSE)

        for (dir in subdirs) {
            matches <- list.files(paths[[dir]], full.names = FALSE) %>%
                .[startsWith(., file_name)]
            if (length(matches) > 0) {
                row[[dir]] <- TRUE
            } else {
                row[[dir]] <- FALSE
            }
        }



        all_data <- all_data %>%
            dplyr::bind_rows(tibble::as_tibble(row))

        print(paste("Parsed file:", file))
    }

    all_data <- all_data %>%
        dplyr::mutate(
            complete = dplyr::if_all(subdirs, identity),
            timestamp = current_timestamp
        )

    export_data_as_parquet(
        data = all_data,
        filename = "tracker_metadata",
        output_root = file.path(paths$output_root, "tables"),
        suffix = ""
    )
}

main()
