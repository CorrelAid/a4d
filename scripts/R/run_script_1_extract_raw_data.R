options(readxl.show_progress = FALSE)

main <- function() {
    paths <- init_paths(c("patient_data_raw", "product_data_raw"), delete = TRUE)
    setup_logger(paths$output_root, "script1")
    tracker_files <- get_files(paths$tracker_root)
    logInfo(
        log_to_json(
            "Found {values['len']} xlsx files under {values['root']}.",
            values = list(len = length(tracker_files), root = paths$tracker_root),
            script = "script1",
            file = "run_script_1_extract_raw_data.R",
            functionName = "main"
        )
    )

    synonyms <- get_synonyms()

    for (i in seq_along(tracker_files)) {
        tracker_file <- tracker_files[i]
        tracker_name <- tools::file_path_sans_ext(basename(tracker_file))
        tictoc::tic(paste("Processing tracker file:", tracker_name))
        process_tracker_file(paths, tracker_file, tracker_name, synonyms)
        tictoc::toc()
        cat(paste("Processed ", i, " of ", length(tracker_files), " (", round(i / length(tracker_files) * 100, 0), "%) tracker files.\n"))
    }
}

# profvis(main())
main()

clearLoggers()
