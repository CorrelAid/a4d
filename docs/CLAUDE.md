# CLAUDE.md

Python pipeline for A4D medical tracker data — processes Excel trackers into BigQuery tables.
Patient pipeline is complete and deployed to production (Cloud Run).

## Module Overview

| Module | Purpose |
|--------|---------|
| `extract/patient.py` | Read Excel trackers → raw parquet (openpyxl, multi-sheet) |
| `extract/product.py` | Read Excel trackers → raw product parquet (month sheets, stock section) |
| `extract/wide_format.py` | Mandalay wide-format handling (column expansion 2020-21; cell splitting 2017-19) |
| `clean/patient.py` | Type conversion, validation, transformations → cleaned parquet |
| `clean/product.py` | Product cleaning pipeline (R steps 2.0-2.21) → cleaned product parquet |
| `clean/schema.py` | 83-column patient meta schema matching R output |
| `clean/schema_product.py` | 20-column product meta schema + helpers |
| `clean/converters.py` | Safe type conversion with ErrorCollector |
| `clean/validators.py` | Case-insensitive allowed-values validation |
| `clean/transformers.py` | Explicit transformations (regimen, BP splitting, FBG) |
| `clean/date_parser.py` | Flexible date parsing (Excel serials, DD/MM/YYYY, month-year) |
| `tables/patient.py` | Aggregate cleaned parquets → static, monthly, annual tables |
| `tables/product.py` | Aggregate cleaned product parquets → product_data table |
| `tables/clinic.py` | Create clinic static table from reference_data/clinic_data.xlsx |
| `tables/logs.py` | Aggregate error logs → logs table |
| `tables/metadata.py` | Tracker metadata table (MD5 + per-tracker output presence flags) |
| `pipeline/patient.py` | Orchestrate extract+clean per tracker, parallel workers |
| `pipeline/product.py` | Product pipeline orchestration (mirrors patient, single product_data table) |
| `pipeline/tracker.py` | Per-tracker pipeline execution (patient + product) |
| `pipeline/models.py` | Result dataclasses |
| `gcp/storage.py` | GCS download/upload |
| `gcp/bigquery.py` | BigQuery table load |
| `gcp/drive.py` | Google Drive download (clinic_data.xlsx); file ID hardcoded in module |
| `reference/synonyms.py` | Column name synonym mapping (YAML) |
| `reference/products.py` | Stock_Summary product reference loader (known products, categories) |
| `reference/provinces.py` | Allowed province validation |
| `reference/loaders.py` | YAML loading utilities |
| `state/` | Reserved for incremental-processing logic (design in [migration/MIGRATION_GUIDE.md](migration/MIGRATION_GUIDE.md); not yet implemented) |
| `utils/` | Shared utilities |
| `config.py` | Pydantic settings from `.env` / `A4D_*` env vars |
| `logging.py` | loguru setup, `file_logger()` context manager |
| `errors.py` | Shared error types |
| `cli.py` | Typer CLI entry point |

## CLI Commands

```bash
uv run a4d process-patient          # Extract + clean + tables (local run, patient)
uv run a4d process-product          # Extract + clean + table (local run, product)
uv run a4d create-tables            # Re-create patient/logs/clinic tables from existing cleaned parquets
uv run a4d create-product-tables    # Re-create product table from existing cleaned parquets
uv run a4d upload-tables            # Upload tables to BigQuery
uv run a4d download-trackers        # Download tracker files from GCS
uv run a4d upload-output            # Upload output directory to GCS
uv run a4d download-reference-data  # Download clinic_data.xlsx from Google Drive into reference_data/
uv run a4d run-pipeline             # Full end-to-end pipeline (patient + product arms, drive/GCS/BigQuery)
```

Key options: `--file` (single tracker), `--workers N`, `--skip-tables`, `--skip-download`, `--skip-upload`, `--skip-drive-download`, `--skip-product`, `--incremental` (skip trackers matching previous run's manifest).

## Output Directory Structure

```text
output/
├── patient_data_raw/       # Raw extracted patient parquets (one per tracker)
├── patient_data_cleaned/   # Cleaned patient parquets (one per tracker)
├── product_data_raw/       # Raw extracted product parquets (one per tracker)
├── product_data_cleaned/   # Cleaned product parquets (one per tracker)
├── tables/                 # Final tables: patient_data_{static,monthly,annual}.parquet, product_data.parquet, clinic_data_static.parquet, table_logs.parquet, tracker_metadata.parquet
└── logs/                   # Per-tracker log files (JSON)
```

## Key Facts

- `clinic_id` = parent folder name of the tracker file
- Year detected from sheet names (`Jan24` → 2024) or filename
- Error sentinel values: numeric `999999`, string `"Undefined"`, date `"9999-09-09"`
- `ErrorCollector` accumulates row-level data quality errors; never raises
- `reference_data/` is shared with the archived R pipeline — changes may affect R logic

## Migration Status

- **Patient pipeline**: complete, validated against 174 trackers, deployed to production
- **Product pipeline**: complete, merged into `src/a4d/` (2026-04-23).
- **Tracker metadata table**: generated on every `create-tables` / `run-pipeline` run (MD5 + output-presence flags) and uploaded to BigQuery `tracker_metadata`.
- **Incremental processing**: shipped 2026-05-01 behind the `--incremental` CLI flag (opt-in) on `process-patient`, `process-product`, and `run-pipeline`. Skips trackers whose MD5 + completion state match the previous run's manifest (BigQuery → local parquet → empty fallback). Default behaviour unchanged. See `a4d.state` module + [migration/MIGRATION_GUIDE.md](migration/MIGRATION_GUIDE.md) state-management section.
