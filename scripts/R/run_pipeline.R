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

config <- config::get()
data_dir <- config$data_root
output_dir <- file.path(data_dir, "output")
# WARNING: this deletes all tracker files, only run on VM where we download them again!
unlink(file.path(data_dir, "*"), recursive = T, force = T)
unlink(output_dir, recursive = T, force = T)
table_dir <- file.path(output_dir, "tables")

download_data(bucket = config$download_bucket, data_dir = data_dir)
source("scripts/R/run_script_1_extract_raw_data.R") # creates CSV files in subfolders patient_data_raw and product_data_raw
source("scripts/R/run_script_2_clean_data.R") # creates CSV files in subfolders patient_data_cleaned and product_data_cleaned
source("scripts/R/run_script_3_create_tables.R") # creates final CSV files in subfolder tables
source("scripts/R/run_script_4_create_logs_table.R")
source("scripts/R/run_script_5_create_metadata_table.R")
upload_data(bucket = config$upload_bucket, data_dir = output_dir)
ingest_data(
    project_id = config$project_id,
    cluster_fields = "clinic_id,patient_id,tracker_date",
    dataset = config$dataset,
    table = "patient_data_monthly",
    source = file.path(table_dir, "patient_data_monthly.parquet")
)
ingest_data(
    project_id = config$project_id,
    cluster_fields = "clinic_id,patient_id,tracker_date",
    dataset = config$dataset,
    table = "patient_data_static",
    source = file.path(table_dir, "patient_data_static.parquet")
)
ingest_data(
    project_id = config$project_id,
    cluster_fields = "clinic_id,patient_id,tracker_date",
    dataset = config$dataset,
    table = "patient_data_hba1c",
    source = file.path(table_dir, "longitudinal_data_hba1c.parquet")
)
ingest_data(
    project_id = config$project_id,
    cluster_fields = "clinic_id,product_released_to,product_table_year,product_table_month",
    dataset = config$dataset,
    table = "product_data",
    source = file.path(table_dir, "product_data.parquet")
)
ingest_data(
    project_id = config$project_id,
    cluster_fields = "clinic_id",
    dataset = config$dataset,
    table = "clinic_data_static",
    source = file.path(table_dir, "clinic_data_static.parquet")
)
ingest_data(
    project_id = config$project_id,
    cluster_fields = "functionName,errorCode,warningCode,fileName",
    dataset = config$dataset,
    table = "logs",
    source = file.path(table_dir, "table_logs.parquet")
)
ingest_data(
    project_id = config$project_id,
    cluster_fields = "file_name,clinic_code",
    dataset = config$dataset,
    table = "tracker_metadata",
    source = file.path(table_dir, "tracker_metadata.parquet")
)
