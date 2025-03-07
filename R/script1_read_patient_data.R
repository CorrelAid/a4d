#' @title Reading patient data from the tracker data file
#'
#' @description
#' This function reads the patient data from the tracker data file,
#' harmonizes the columns, and returns the data as a data frame.
#'
#' @param tracker_data_file The path to the tracker data file.
#' @param columns_synonyms A named list of column synonyms.
#'
#' @return A data frame with the patient data.
#'
#' @export
reading_patient_data <-
    function(tracker_data_file, columns_synonyms) {
        sheet_list <- readxl::excel_sheets(tracker_data_file)
        testit::assert(length(sheet_list) > 0)

        logInfo(
            log_to_json(
                message = "Found {values['len']} sheets: {values['sheets']}.",
                values = list(len = length(sheet_list), sheets = sheet_list),
                script = "script1",
                file = "script1_read_patient_data.R",
                functionName = "reading_patient_data"
            )
        )

        month_list <-
            sheet_list[na.omit(pmatch(month.abb, sheet_list))]
        testit::assert(length(month_list) > 0)

        logInfo(
            log_to_json(
                message = "Found {values['len']} month sheets: {values['months']}.",
                values = list(len = length(month_list), months = month_list),
                script = "script1",
                file = "script1_read_patient_data.R",
                functionName = "reading_patient_data"
            )
        )

        # Extract year
        year <- get_tracker_year(tracker_data_file, month_list)
        logInfo(
            log_to_json(
                message = "Tracker year = {values['year']}.",
                values = list(year = year),
                script = "script1",
                file = "script1_read_patient_data.R",
                functionName = "reading_patient_data"
            )
        )

        testit::assert(year >= 2017 & year <= 2024)

        tidy_tracker_list <- NULL

        for (curr_sheet in month_list) {
            df_patient <- extract_patient_data(tracker_data_file, curr_sheet, year)
            testit::assert(nrow(df_patient) > 0)

            df_patient <-
                harmonize_patient_data_columns(df_patient, columns_synonyms)
            testit::assert("patient_id" %in% colnames(df_patient))

            # -- if we have duplicate columns, merge them
            if (anyDuplicated(colnames(df_patient)) > 0) {
                duplicated_cols <- colnames(df_patient) %>%
                    table() %>%
                    dplyr::as_tibble() %>%
                    dplyr::filter(n > 1) %>%
                    dplyr::select(1) %>%
                    dplyr::pull()
                for (col in duplicated_cols) {
                    mask <- colnames(df_patient) == col
                    merged_col <- df_patient[mask] %>%
                        tidyr::unite(!!col, sep = ",")
                    df_patient <- df_patient[!mask]
                    df_patient <- df_patient %>%
                        tibble::add_column(!!col := dplyr::pull(merged_col), .name_repair = "minimal")
                }
            }

            # add the current sheet name, month name and year to the patient data frame
            df_patient <- df_patient %>%
                dplyr::mutate(
                    sheet_name = curr_sheet,
                    tracker_month = match(substr(curr_sheet, 1, 3), month.abb),
                    tracker_year = year
                )

            tidy_tracker_list[[curr_sheet]] <- df_patient
        }

        df_raw <- dplyr::bind_rows(tidy_tracker_list)


        # filter all rows with no patient id or patient name
        df_raw <- df_raw %>%
            dplyr::filter(!(is.na(patient_id) & is.na(name))) %>%
            dplyr::filter(!(patient_id == "0" & name == "0"))

        if ("Patient List" %in% sheet_list) {
            patient_list <- extract_patient_data(
                tracker_data_file,
                "Patient List",
                year
            )
            testit::assert(nrow(patient_list) > 0)
            patient_list <- harmonize_patient_data_columns(
                patient_list,
                columns_synonyms
            )
            testit::assert("patient_id" %in% colnames(patient_list))

            patient_list <- patient_list %>%
                dplyr::filter(!(is.na(patient_id) & is.na(name))) %>%
                dplyr::filter(!(patient_id == "0" & name == "0"))

            df_raw <- dplyr::left_join(
                df_raw %>% dplyr::select(-any_of(c("hba1c_baseline"))),
                patient_list %>%
                    dplyr::select(-any_of(c(
                        "name"
                    ))),
                by = "patient_id",
                relationship = "many-to-one",
                suffix = c(".monthly", ".static")
            )
        }

        if ("Annual" %in% sheet_list) {
            annual_data <- extract_patient_data(
                tracker_data_file,
                "Annual",
                year
            )
            testit::assert(nrow(annual_data) > 0)
            annual_data <- harmonize_patient_data_columns(
                annual_data,
                columns_synonyms
            )
            testit::assert("patient_id" %in% colnames(annual_data))

            annual_data <- annual_data %>%
                dplyr::filter(!(is.na(patient_id) & is.na(name))) %>%
                dplyr::filter(!(patient_id == "0" & name == "0"))

            df_raw <- dplyr::left_join(
                df_raw,
                annual_data %>%
                    dplyr::select(-any_of(c(
                        "status",
                        "name"
                    ))),
                by = "patient_id",
                relationship = "many-to-one",
                suffix = c(".monthly", ".annual")
            )
        }

        df_raw
    }
