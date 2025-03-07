# current time
current_timestamp <- Sys.time()

main <- function() {
    paths <- init_paths(c("logs", "tables"), delete = FALSE)
    logFiles <- get_files(paths$logs, pattern = "*.log")
    allLogs <- tibble::tibble()

    for (file in logFiles) {
        tryCatch(
            {
                filePath <- file.path(paths$logs, file)
                fileConnection <- file(filePath, open = "r")
                lines <- readLines(fileConnection)
                close(fileConnection)

                if (!is.null(lines)) {
                    result <- parseLines(lines) %>%
                        dplyr::mutate(fileName = file)
                    allLogs <- allLogs %>%
                        dplyr::bind_rows(result)
                }

                print(paste("Parsed file:", file))
            },
            error = function(cond) {
                message("Error message:")
                message(conditionMessage(cond))
                NA
            },
            warning = function(cond) {
                message("Warning message:")
                message(conditionMessage(cond))
                NULL
            }
        )
    }

    eventLogs <- allLogs %>%
        dplyr::mutate(across(where(is.character), as.factor)) %>%
        dplyr::mutate(Message = as.character(Message)) %>%
        dplyr::filter(substr(Message, 1, 1) == "{") %>%
        dplyr::mutate(Message = purrr::map(Message, ~ jsonlite::fromJSON(.) %>%
            lapply(., function(x) if (is.null(x)) NA else if (is.list(x)) toString(x) else x) %>%
            tibble::as_tibble())) %>%
        tidyr::unnest(Message) %>%
        dplyr::rename(Message = message) %>%
        dplyr::mutate(across(c("file", "errorCode", "warningCode", "functionName"), factor))

    export_data_as_parquet(
        data = eventLogs,
        filename = "table_logs",
        output_root = paths$tables,
        suffix = ""
    )
}

parseLines <- function(lines) {
    rows <- strsplit(lines, "\t")
    malformed <- sapply(rows, function(x) length(x) != 6)
    rows <- rows[!malformed]
    result <- data.frame(
        Timestamp = current_timestamp, # current time
        # Thread = sapply(rows, function(x) x[2]),
        Level = sapply(rows, function(x) x[3]),
        # Package = sapply(rows, function(x) x[4]),
        # Function = sapply(rows, function(x) x[5]),
        Message = sapply(rows, function(x) x[6])
    )
    return(result)
}

main()
