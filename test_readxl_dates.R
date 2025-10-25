#!/usr/bin/env Rscript

# Test what readxl returns for dates when col_types = "text"
library(readxl)

tracker_file <- "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Malaysia/SBU/2024_Sibu Hospital A4D Tracker.xlsx"

cat("Testing readxl with different col_types settings:\n\n")

# Test 1: Let readxl guess types (default) - read date values in column C
cat("1. Default (readxl guesses types):\n")
df_auto <- read_excel(tracker_file, sheet = "Jan24", range = "C6:C8", col_names = FALSE)
print(df_auto)
cat("\nColumn types:\n")
print(sapply(df_auto, class))
cat("\nValues:\n")
print(df_auto[[1]])

cat("\n" , rep("=", 60), "\n\n")

# Test 2: Force all columns to text
cat("2. Force col_types = 'text':\n")
df_text <- read_excel(tracker_file, sheet = "Jan24", range = "C6:C8", col_names = FALSE, col_types = "text")
print(df_text)
cat("\nColumn types:\n")
print(sapply(df_text, class))
cat("\nActual values (as text):\n")
print(df_text[[1]])
cat("\n")
cat("First value details:\n")
cat(sprintf("Value: '%s'\n", df_text[[1]][1]))
cat(sprintf("Is numeric: %s\n", !is.na(as.numeric(df_text[[1]][1]))))
