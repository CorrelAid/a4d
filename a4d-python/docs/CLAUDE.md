# CLAUDE.md

Python pipeline for A4D medical tracker data — processes Excel trackers into BigQuery tables.
Patient pipeline is complete and tested locally. Product pipeline is not yet started.

## Module Overview

| Module | Purpose |
|--------|---------|
| `extract/patient.py` | Read Excel trackers → raw parquet (openpyxl, multi-sheet) |
| `clean/patient.py` | Type conversion, validation, transformations → cleaned parquet |
| `clean/schema.py` | 83-column meta schema matching R output |
| `clean/converters.py` | Safe type conversion with ErrorCollector |
| `clean/validators.py` | Case-insensitive allowed-values validation |
| `clean/transformers.py` | Explicit transformations (regimen, BP splitting, FBG) |
| `clean/date_parser.py` | Flexible date parsing (Excel serials, DD/MM/YYYY, month-year) |
| `tables/patient.py` | Aggregate cleaned parquets → static, monthly, annual tables |
| `tables/logs.py` | Aggregate error logs → logs table |
| `pipeline/patient.py` | Orchestrate extract+clean per tracker, parallel workers |
| `pipeline/tracker.py` | Per-tracker pipeline execution |
| `pipeline/models.py` | Result dataclasses |
| `gcp/storage.py` | GCS download/upload |
| `gcp/bigquery.py` | BigQuery table load |
| `reference/synonyms.py` | Column name synonym mapping (YAML) |
| `reference/provinces.py` | Allowed province validation |
| `reference/loaders.py` | YAML loading utilities |
| `state/` | State management module (exists, not yet wired into pipeline) |
| `utils/` | Shared utilities |
| `config.py` | Pydantic settings from `.env` / `A4D_*` env vars |
| `logging.py` | loguru setup, `file_logger()` context manager |
| `errors.py` | Shared error types |
| `cli.py` | Typer CLI entry point |

## CLI Commands

```bash
uv run a4d process-patient          # Extract + clean + tables (local run)
uv run a4d create-tables            # Re-create tables from existing cleaned parquets
uv run a4d upload-tables            # Upload tables to BigQuery
uv run a4d download-trackers        # Download tracker files from GCS
uv run a4d upload-output            # Upload output directory to GCS
uv run a4d run-pipeline             # Full end-to-end pipeline (download→process→upload)
```

Key options: `--file` (single tracker), `--workers N`, `--force`, `--skip-tables`, `--skip-download`, `--skip-upload`.

## Output Directory Structure

```
output/
├── patient_data_raw/       # Raw extracted parquets (one per tracker)
├── patient_data_cleaned/   # Cleaned parquets (one per tracker)
├── tables/                 # Final tables: static.parquet, monthly.parquet, annual.parquet, logs.parquet
└── logs/                   # Per-tracker log files (JSON)
```

## Key Facts

- `clinic_id` = parent folder name of the tracker file
- Year detected from sheet names (`Jan24` → 2024) or filename
- Error sentinel values: numeric `999999`, string `"Undefined"`, date `"9999-09-09"`
- `ErrorCollector` accumulates row-level data quality errors; never raises
- `reference_data/` is shared with the R pipeline — changes affect both

## Migration Status

- **Patient pipeline**: complete, validated against 174 trackers locally
- **Product pipeline**: not yet started
- **GCP production run**: next step (Phase 8)
- **State management**: module exists but not wired into pipeline yet
