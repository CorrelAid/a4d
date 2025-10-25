#!/usr/bin/env Rscript

# Test the fixed parse_dates function
source("R/script2_helper_patient_data_fix.R")

cat("Testing parse_dates() with Excel serial numbers:\n\n")

test_dates <- c(
    "45341.0",   # Should be 2024-02-19
    "39920.0",   # Should be 2009-04-17
    "44782.0",   # Should be 2022-08-09
    "2024-01-01", # Should parse as regular date
    "19-Apr-2009" # Should parse with lubridate
)

for (date_str in test_dates) {
    result <- parse_dates(date_str)
    cat(sprintf("Input: '%s' -> Output: %s\n", date_str, as.character(result)))
}

cat("\nVerifying Excel serial number conversion:\n")
cat("45341.0 should be 2024-02-19:\n")
result <- parse_dates("45341.0")
cat(sprintf("  Got: %s\n", as.character(result)))
cat(sprintf("  Correct: %s\n", as.character(result) == "2024-02-19"))
