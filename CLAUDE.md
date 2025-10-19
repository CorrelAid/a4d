# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an R package for processing, cleaning, and ingesting medical tracker data (Excel files) for the CorrelAid A4D project.
The package extracts patient and product data from Excel trackers, validates and cleans the data, and creates structured tables for ingestion into Google BigQuery.

## Package Structure

This project uses the R package development workflow with `devtools` and `renv` for dependency management. The codebase follows a structured pipeline architecture:

1. **Script 1**: Extract raw data (patient and product data) from Excel tracker files
2. **Script 2**: Clean and validate extracted data
3. **Script 3**: Create final database tables
4. **Script 4**: Create logs table
5. **Script 5**: Create metadata table

## Essential Commands

### Initial Setup

```r
# Install dependencies (first time only)
renv::restore()

# Install devtools for development (not tracked by renv)
install.packages("devtools")

# Load all package functions
devtools::load_all()
```

### Development Workflow

```r
# Create new R function file
usethis::use_r("function_name")

# Create new test file
usethis::use_test("function_name")

# Load and test changes
devtools::load_all()

# Run all tests
devtools::test()

# Check package for issues
devtools::check()

# Update documentation (after adding/editing roxygen comments)
devtools::document()
```

### Adding Dependencies

```r
# Add package to DESCRIPTION file
usethis::use_package("package_name")

# Install for development only (not in DESCRIPTION)
renv::install("package_name")

# Update lockfile after installing new packages
renv::snapshot()
```

### Running the Pipeline

```r
# Individual scripts (in order)
source("scripts/R/run_script_1_extract_raw_data.R")
source("scripts/R/run_script_2_clean_data.R")
source("scripts/R/run_script_3_create_tables.R")
source("scripts/R/run_script_4_create_logs_table.R")
source("scripts/R/run_script_5_create_metadata_table.R")

# Full pipeline (includes GCP upload/download)
source("scripts/R/run_pipeline.R")
```

### Data Path Configuration

Set the data root path to avoid re-selecting tracker files:

```r
# Open .Renviron file
usethis::edit_r_environ()

# Add this line (replace with your path)
A4D_DATA_ROOT = "/path/to/your/tracker/files"
```

## Architecture

### Data Flow

```
Excel Trackers → Script 1 (Extract) → Raw Parquet Files
                                            ↓
                                      Script 2 (Clean) → Cleaned Parquet Files
                                            ↓
                                      Script 3 (Tables) → Final Parquet Tables
                                            ↓
                                      BigQuery Ingestion
```

### Key Directories

- **R/**: Package functions organized by script number
  - `script1_*.R`: Raw data extraction functions
  - `script2_*.R`: Data cleaning and validation functions
  - `script3_*.R`: Table creation functions
  - `helper_*.R`: Shared utility functions
  - `logger.R`: JSON-based logging infrastructure

- **scripts/R/**: Executable pipeline scripts that orchestrate the functions

- **reference_data/**: Configuration and master data
  - `master_tracker_variables.xlsx`: Variable codebook
  - `clinic_data.xlsx`: Clinic reference data (downloaded from Google Sheets)
  - `data_cleaning.yaml`: Data validation and cleaning rules
  - `synonyms/`: YAML files mapping column name variations to standard names

- **tests/testthat/**: Unit tests

### Synonym System

The package handles variability in Excel column names through a synonym mapping system:
- Synonyms are defined in YAML files under `reference_data/synonyms/`
- Loaded via `get_synonyms()` and used throughout extraction
- New synonyms can be added to handle tracker variations

### Logging

All scripts use structured JSON logging via the `ParallelLogger` package:
- Logs are written to `output/logs/`
- Use `log_to_json()` to create structured log messages
- Each file being processed gets its own log file via `with_file_logger()`
- Log viewer Shiny app available in `tools/LogViewerA4D/`

### Error Handling

Standard error values are used throughout:
- Numeric errors: `999999`
- Character errors: `"Undefined"`
- Date errors: `"9999-09-09"`

## Configuration

The `config.yml` file contains environment-specific settings:
- GCP bucket paths for data download/upload
- Local data root directory
- BigQuery project and dataset names

Use `config::get()` to load configuration for the current environment.

## Git Workflow

1. Work on the `develop` branch (not `main`)
2. Create feature branches: `git checkout -b <issue-no>-<title>`
3. After changes, merge latest develop: `git merge develop`
4. Create PR targeting `develop` (not `main`)
5. Check GitHub workflows for CI/CD status

## Output Tables

The pipeline creates these final tables:
- `patient_data_monthly`: Monthly patient observations
- `patient_data_annual`: Annual patient data
- `patient_data_static`: Static patient attributes
- `patient_data_hba1c`: Longitudinal HbA1c measurements
- `product_data`: Product/supply distribution data
- `clinic_data_static`: Clinic reference information
- `logs`: Structured log messages from processing
- `tracker_metadata`: Metadata about processed tracker files
