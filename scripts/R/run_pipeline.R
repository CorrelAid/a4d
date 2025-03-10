BUCKET_DOWLOAD <- "a4dphase2_upload"
BUCKET_UPLOAD <- "a4dphase2_output"

# local
Sys.setenv(A4D_DATA_ROOT = "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload")
# Sys.setenv(A4D_DATA_ROOT = "/Users/miay/Library/CloudStorage/OneDrive-Personal/1 Projects/Ehrenamt/A4D/docs/tracker/2024")
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
# WARNING: this deletes all tracker files, only run on VM where we download them again!
unlink(file.path(data_dir, "*"), recursive = T, force = T)
unlink(output_dir, recursive = T, force = T)
table_dir <- file.path(output_dir, "tables")

download_data(bucket = BUCKET_DOWLOAD, data_dir = data_dir)
source("scripts/R/run_script_1_extract_raw_data.R") # creates CSV files in subfolders patient_data_raw and product_data_raw
source("scripts/R/run_script_2_clean_data.R") # creates CSV files in subfolders patient_data_cleaned and product_data_cleaned
source("scripts/R/run_script_3_create_tables.R") # creates final CSV files in subfolder tables
source("scripts/R/run_script_4_ingest_logs.R")
upload_data(bucket = BUCKET_UPLOAD, data_dir = output_dir)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "clinic_id,patient_id,tracker_date",
    dataset = DATASET,
    table = "patient_data_monthly",
    source = file.path(table_dir, "patient_data_monthly.parquet")
)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "clinic_id,patient_id,tracker_date",
    dataset = DATASET,
    table = "patient_data_static",
    source = file.path(table_dir, "patient_data_static.parquet")
)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "clinic_id,patient_id,tracker_date",
    dataset = DATASET,
    table = "patient_data_hba1c",
    source = file.path(table_dir, "longitudinal_data_hba1c.parquet")
)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "clinic_id,product_released_to,product_table_year,product_table_month",
    dataset = DATASET,
    table = "product_data",
    source = file.path(table_dir, "product_data.parquet")
)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "clinic_id",
    dataset = DATASET,
    table = "clinic_data_static",
    source = file.path(table_dir, "clinic_data_static.parquet")
)
ingest_data(
    project_id = PROJECT_ID,
    cluster_fields = "functionName,errorCode,warningCode,fileName",
    dataset = DATASET,
    table = "logs",
    source = file.path(table_dir, "table_logs.parquet")
)
