options(readxl.show_progress = FALSE)

BUCKET_DOWLOAD <- "a4dphase2_upload"
BUCKET_UPLOAD <- "a4dphase2_output"

# local
Sys.setenv(A4D_DATA_ROOT = "/Volumes/USB SanDisk 3.2Gen1 Media/a4d")
PROJECT_ID <- "a4d-315220"
DATASET <- "tracker"

# VM
Sys.setenv(A4D_DATA_ROOT = "/home/rstudio/data")
PROJECT_ID <- "a4dphase2"
DATASET <- "tracker"

download_data <- function(bucket, data_dir) {
    print("Start downloading data from GCP Storage")
    command <- paste("gsutil -m cp -r", paste0("gs://", bucket), data_dir)
    exit_code <- system(command)
    if (exit_code != 0) {
        paste("Error while executing", command)
        stop("Error during downloading data")
    }
    print("Finished downloading data from GCP Storage")
}

upload_data <- function(bucket, data_dir) {
    print("Start uploading data to GCP Storage")
    command <- paste("gsutil -m cp -r", data_dir, paste0("gs://", bucket))
    exit_code <- system(command)
    if (exit_code != 0) {
        paste("Error while executing", command)
        stop("Error during uploading data")
    }
    print("Finished uploading data to GCP Storage")
}

ingest_data <- function(project_id, cluster_fields, dataset, table, source) {
    print("Deleting old table in GCP Big Query")
    command <- paste(
        "bq rm",
        "-f",
        "-t",
        paste0(project_id, ":", dataset, ".", table)
    )
    cat(command)
    exit_code <- system(command)
    if (exit_code != 0) {
        paste("Error while executing", command)
        stop("Error during ingesting data")
    }

    print("Ingesting data to GCP Big Query")
    command <- paste(
        "bq load",
        "--source_format=PARQUET",
        paste0("--project_id=", project_id),
        "--max_bad_records=0",
        "--replace=true",
        paste0("--clustering_fields=", cluster_fields),
        paste0(dataset, ".", table),
        source
    )
    cat(command)
    exit_code <- system(command)
    if (exit_code != 0) {
        paste("Error while executing", command)
        stop("Error during ingesting data")
    }
    print("Finished ingesting data to GCP Big Query")
}

data_dir <- select_A4D_directory()
output_dir <- file.path(data_dir, "output")
unlink(output_dir, recursive = T, force = T)
table_dir <- file.path(output_dir, "tables")

download_data(bucket = BUCKET_DOWLOAD, data_dir = data_dir)

paths <- init_paths(c("patient_data_raw", "patient_data_cleaned", "product_data_raw", "product_data_cleaned", "tables"), delete = TRUE)
setup_logger(paths$output_root)
tracker_files <- get_files(paths$tracker_root)
logInfo("Found ", length(tracker_files), " tracker files.")

all_patient_data <- list()
all_product_data <- list()
for (i in seq_along(tracker_files)) {
    tracker_file <- tracker_files[i]
    tracker_name <- tools::file_path_sans_ext(basename(tracker_file))

    logInfo("Start processing tracker file ", tracker_file, ".")
    tictoc::tic("process tracker file")

    logfile <- paste0(tracker_name, "_", "script_01")
    raw_data <- with_file_logger(logfile,
        {
            tryCatch(
                process_tracker_file(
                    tracker_file = tracker_file,
                    tracker_name = tracker_name,
                    tracker_root = paths$tracker_root,
                    output_folder = paths$patient_data_raw,
                    export = FALSE
                ),
                error = function(e) {
                    logError("Could not process tracker file. Error = ", e$message, ".")
                },
                warning = function(w) {
                    logWarn("Could not process tracker file. Warning = ", w$message, ".")
                }
            )
        },
        output_root = paths$output_root
    )
    tictoc::toc()

    logInfo("Raw patient data: ", paste(dim(raw_data$patients), collapse = ", "))
    logInfo("Raw product data: ", paste(dim(raw_data$products), collapse = ", "))

    tictoc::tic("process patient data")

    data <- list()
    logfile <- paste0(tracker_name, "_", "script_02_patient")
    data$patients <- with_file_logger(logfile,
        {
            tryCatch(
                process_patient_data(
                    raw_patient_data = raw_data$patients,
                    tracker_name = tracker_name,
                    output_folder = paths$patient_data_cleaned,
                    export = FALSE
                ),
                error = function(e) {
                    logError("Could not process raw patient data Error = ", e$message, ".")
                },
                warning = function(w) {
                    logWarn("Could not process raw product data. Warning = ", w$message, ".")
                }
            )
        },
        output_root = paths$output_root
    )
    tictoc::toc()

    tictoc::tic("process product data")

    logfile <- paste0(tracker_name, "_", "script_02_product")
    data$products <- with_file_logger(logfile,
        {
            tryCatch(
                process_product_data(
                    raw_product_data = raw_data$products,
                    tracker_name = tracker_name,
                    output_folder = paths$product_data_cleaned,
                    export = FALSE
                ),
                error = function(e) {
                    logError("Could not process raw patient data Error = ", e$message, ".")
                },
                warning = function(w) {
                    logWarn("Could not process raw product data. Warning = ", w$message, ".")
                }
            )
        },
        output_root = paths$output_root
    )
    tictoc::toc()

    logInfo("Cleaned patient data: ", paste(dim(data$patients), collapse = ", "))
    logInfo("Cleaned product data: ", paste(dim(data$products), collapse = ", "))

    all_patient_data[[tracker_name]] <- data$patients
    all_product_data[[tracker_name]] <- data$products

    logInfo("Finished processing tracker file ", tracker_file, ".")
    cat("Finished processing ", i, " of ", length(tracker_files), " (", round(i / length(tracker_files) * 100), "%) tracker files.\n")
}

logInfo("Start creating table csv files.")

logfile <- "table_patient_data_static"
with_file_logger(logfile,
    {
        tryCatch(
            {
                create_table_patient_data_static(all_patient_data, paths$tables)
            },
            error = function(e) {
                logError("Could not create table csv for static patient data. Error: ", e$message)
            },
            warning = function(w) {
                logWarn("Could not create table csv for static patient data. Error: ", w$message)
            }
        )
    },
    output_root = paths$output_root
)

logfile <- "table_patient_data_monthly"
with_file_logger(logfile,
    {
        tryCatch(
            {
                create_table_patient_data_monthly(all_patient_data, paths$tables)
            },
            error = function(e) {
                logError("Could not create table csv for monthly patient data. Error: ", e$message)
            },
            warning = function(w) {
                logWarn("Could not create table csv for monthly patient data. Error: ", w$message)
            }
        )
    },
    output_root = paths$output_root
)

logfile <- "table_longitudinal_data_hba1c"
with_file_logger(logfile,
    {
        tryCatch(
            {
                create_table_longitudinal_data(
                    all_patient_data,
                    paths$tables,
                    "hba1c_updated",
                    "hba1c"
                )
            },
            error = function(e) {
                logError("Could not create table csv for longitudinal patient data. Error: ", e$message)
            },
            warning = function(w) {
                logWarn("Could not create table csv for longitudinal patient data. Error: ", w$message)
            }
        )
    },
    output_root = paths$output_root
)

logfile <- "table_product_data"
with_file_logger(logfile,
    {
        tryCatch(
            {
                create_table_product_data(all_product_data, paths$tables)
            },
            error = function(e) {
                logError("Could not create table for product data. Error: ", e$message)
            },
            warning = function(w) {
                logWarn("Could not create table for product data. Warning: ", w$message)
            }
        )
    },
    output_root = paths$output_root
)

logfile <- "clinic_data_static"
with_file_logger(logfile,
    {
        tryCatch(
            {
                export_data_as_parquet(
                    data = read.csv("reference_data/clinic_data_static.csv"),
                    filename = "clinic_data_static",
                    output_folder = paths$tables,
                    suffix = ""
                )
            },
            error = function(e) {
                logError("Could not create clinic data static table. Error: ", e$message)
            },
            warning = function(w) {
                logWarn("Could not create clinic data static table. Warning: ", w$message)
            }
        )
    },
    output_root = paths$output_root
)

logInfo("Finish creating table files.")

logInfo("Trying to link files for product and patient data.")

logfile <- "link_product_patient_data"
with_file_logger(logfile,
    {
        tryCatch(
            {
                link_product_patient(
                    file.path(paths$tables, "product_data.parquet"),
                    file.path(paths$tables, "patient_data_monthly.parquet")
                )
            },
            error = function(e) {
                logError("Could not link files for product and patient data. Error: ", e$message)
            },
            warning = function(w) {
                logWarn("Could not link files for product and patient data. Warning: ", w$message)
            }
        )
    },
    output_root = paths$output_root
)

logInfo("Finished linking files for product and patient data.")

clearLoggers()

# source("scripts/run_script_2_clean_data.R") # creates CSV files in subfolders patient_data_cleaned and product_data_cleaned
# source("scripts/run_script_3_create_tables.R") # creates final CSV files in subfolder tables
upload_data(bucket = BUCKET_UPLOAD, data_dir = output_dir)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "clinic_code,id,tracker_year,tracker_month",
    dataset = DATASET,
    table = "patient_data_monthly",
    source = file.path(table_dir, "patient_data_monthly.parquet")
)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "id,tracker_year,tracker_month",
    dataset = DATASET,
    table = "patient_data_static",
    source = file.path(table_dir, "patient_data_static.parquet")
)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "clinic_code,id,tracker_year,tracker_month",
    dataset = DATASET,
    table = "patient_data_hba1c",
    source = file.path(table_dir, "longitudinal_data_hba1c.parquet")
)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "product_hospital,product_released_to,product_table_year,product_table_month",
    dataset = DATASET,
    table = "product_data",
    source = file.path(table_dir, "product_data.parquet")
)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "clinic_code",
    dataset = DATASET,
    table = "clinic_data_static",
    source = file.path(table_dir, "clinic_data_static.parquet")
)
