#!/usr/bin/env Rscript
# Test script to run R pipeline steps 1 & 2 on a single tracker file
#
# Usage:
#   Rscript scripts/test_single_tracker.R "/path/to/tracker.xlsx"
#
# Example:
#   Rscript scripts/test_single_tracker.R "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Malaysia/SBU/2023_Sibu Hospital A4D Tracker.xlsx"

library(devtools)

# Load the a4d package
cat("Loading a4d package...\n")
devtools::load_all()

# Get tracker file from command line or use default
args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 0) {
    tracker_file <- args[1]
} else {
    # Default to 2023 Sibu
    tracker_file <- "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Malaysia/SBU/2023_Sibu Hospital A4D Tracker.xlsx"
}

if (!file.exists(tracker_file)) {
    stop("Tracker file not found: ", tracker_file)
}

cat("\n========================================\n")
cat("TESTING R PIPELINE ON SINGLE TRACKER\n")
cat("========================================\n")
cat("File:", tracker_file, "\n")

# Extract tracker name (filename without .xlsx)
tracker_name <- tools::file_path_sans_ext(basename(tracker_file))
cat("Tracker name:", tracker_name, "\n\n")

# Output directory
output_dir <- "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/output"
raw_dir <- file.path(output_dir, "patient_data_raw")
clean_dir <- file.path(output_dir, "patient_data_cleaned")

dir.create(raw_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(clean_dir, showWarnings = FALSE, recursive = TRUE)

# Load synonyms
synonyms <- get_synonyms()

# ============================================
# STEP 1: EXTRACTION
# ============================================
cat("========================================\n")
cat("STEP 1: EXTRACTION (script1)\n")
cat("========================================\n\n")

# Run extraction - this function doesn't return anything
process_tracker_patient_data(
    tracker_name = tracker_name,
    tracker_data_file = tracker_file,
    output_root = raw_dir,
    synonyms_patient = synonyms$patient
)

cat("\n✓ Extraction complete\n")

# Manually construct the output path (function doesn't return it)
raw_output_path <- file.path(raw_dir, paste0(tracker_name, "_patient_raw.parquet"))
cat("Raw output:", raw_output_path, "\n\n")

# Read and inspect raw data
df_raw <- arrow::read_parquet(raw_output_path)
cat("Raw data dimensions:", nrow(df_raw), "rows x", ncol(df_raw), "columns\n")

# Check for columns with 'complication' in name
complication_cols <- names(df_raw)[grepl("complication", names(df_raw), ignore.case = TRUE)]
if (length(complication_cols) > 0) {
    cat("\nColumns with 'complication' in name:\n")
    for (col in complication_cols) {
        non_null <- sum(!is.na(df_raw[[col]]))
        cat("  -", col, ":", non_null, "non-null values\n")
    }
} else {
    cat("\nNo columns with 'complication' in name\n")
}

# Check for columns with 'insulin' in name
insulin_cols <- names(df_raw)[grepl("insulin", names(df_raw), ignore.case = TRUE)]
if (length(insulin_cols) > 0) {
    cat("\nColumns with 'insulin' in name:\n")
    for (col in insulin_cols) {
        non_null <- sum(!is.na(df_raw[[col]]))
        cat("  -", col, ":", non_null, "non-null values\n")
    }
}

# ============================================
# STEP 2: CLEANING
# ============================================
cat("\n========================================\n")
cat("STEP 2: CLEANING (script2)\n")
cat("========================================\n\n")

# Create paths list as expected by the function
paths <- list(
    output_root = output_dir,
    patient_data_cleaned = clean_dir
)

# Run cleaning - this function also doesn't return anything
# patient_file should be relative to output_root
patient_file <- file.path("patient_data_raw", paste0(tracker_name, "_patient_raw.parquet"))
patient_file_name <- paste0(tracker_name, "_patient_raw")

process_raw_patient_file(
    paths = paths,
    patient_file = patient_file,
    patient_file_name = patient_file_name,
    output_root = clean_dir
)

cat("\n✓ Cleaning complete\n")

# Manually construct the output path
clean_output_path <- file.path(clean_dir, paste0(stringr::str_replace(patient_file_name, "_raw", "_cleaned"), ".parquet"))
cat("Clean output:", clean_output_path, "\n\n")

# Read and inspect cleaned data
df_clean <- arrow::read_parquet(clean_output_path)
cat("Cleaned data dimensions:", nrow(df_clean), "rows x", ncol(df_clean), "columns\n")

# Check same columns
complication_cols_clean <- names(df_clean)[grepl("complication", names(df_clean), ignore.case = TRUE)]
if (length(complication_cols_clean) > 0) {
    cat("\nColumns with 'complication' in name (after cleaning):\n")
    for (col in complication_cols_clean) {
        non_null <- sum(!is.na(df_clean[[col]]))
        cat("  -", col, ":", non_null, "non-null values\n")
    }
}

insulin_cols_clean <- names(df_clean)[grepl("insulin", names(df_clean), ignore.case = TRUE)]
if (length(insulin_cols_clean) > 0) {
    cat("\nColumns with 'insulin' in name (after cleaning):\n")
    for (col in insulin_cols_clean) {
        non_null <- sum(!is.na(df_clean[[col]]))
        cat("  -", col, ":", non_null, "non-null values\n")
    }
}

# ============================================
# SUMMARY
# ============================================
cat("\n========================================\n")
cat("SUMMARY\n")
cat("========================================\n\n")
cat("Raw data:    ", nrow(df_raw), "rows,", ncol(df_raw), "columns\n")
cat("Cleaned data:", nrow(df_clean), "rows,", ncol(df_clean), "columns\n")
cat("\nOutput files:\n")
cat("  RAW:  ", raw_output_path, "\n")
cat("  CLEAN:", clean_output_path, "\n")
