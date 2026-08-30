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
| `clean/schema.py` | 85-column patient meta schema every cleaned parquet conforms to |
| `clean/schema_product.py` | 20-column product meta schema + helpers |
| `clean/converters.py` | Safe type conversion, reporting a finding per unusable cell |
| `clean/validators.py` | Case-insensitive allowed-values validation |
| `clean/transformers.py` | Explicit transformations (regimen, BP splitting, FBG) |
| `clean/date_parser.py` | Flexible date parsing (Excel serials, DD/MM/YYYY, month-year) |
| `tables/patient.py` | Aggregate cleaned parquets → static, monthly, annual tables |
| `tables/product.py` | Aggregate cleaned product parquets → product_data table |
| `tables/clinic.py` | Create clinic static table from reference_data/clinic_data.xlsx |
| `tables/logs.py` | Aggregate operational logs → logs table |
| `tables/findings.py` | Aggregate data-quality findings → findings table |
| `tables/metadata.py` | Tracker metadata table (MD5 + per-tracker output presence flags) |
| `validate/source_vs_output_patient.py` | Cell-by-cell check of published patient output against the source workbook |
| `validate/source_vs_output_product.py` | The same for the product arm |
| `validate/snapshot.py` | Golden-master digest of a run's output, and the diff that classifies what moved |
| `validate/snapshot_store.py` | Where the digest baseline lives (on the tracker drive, never committed) |
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
| `logging.py` | loguru setup, `file_logger()` context manager (operational logging only) |
| `findings.py` | Data-quality findings: the single emit point, its context, and the record |
| `cli.py` | Typer CLI entry point |

## CLI Commands

Commands are grouped by process (`run` / `create` / `upload` / `download`), not by the object they act on:

```bash
uv run a4d run                    # Full end-to-end pipeline (patient + product arms, drive/GCS/BigQuery)
uv run a4d run patient            # Extract + clean + tables (local run, patient)
uv run a4d run product            # Extract + clean + table (local run, product)

uv run a4d create tables          # Re-create patient/product/clinic/logs tables from existing cleaned parquets
uv run a4d create logs            # Re-create only the logs table from existing pipeline log files

uv run a4d upload tables          # Upload tables to BigQuery (--only patient|product|clinic|logs|findings|metadata to restrict)
uv run a4d upload output          # Upload output directory to GCS

uv run a4d download trackers      # Download tracker files from GCS
uv run a4d download clinic-data   # Download clinic_data.xlsx from Google Drive into reference_data/

uv run a4d report findings        # Excel of every data-quality finding (--tracker NAME to drill into one, --from-bigquery for a deployed run)

uv run a4d snapshot check     # Digest this run's output and diff it against the accepted baseline
uv run a4d snapshot update    # Accept the last check's digest as the new baseline (runs nothing itself)
```

Key options: `--file` (single tracker), `--workers N`, `--skip-tables`, `--skip-download`, `--skip-upload`, `--skip-drive-download`, `--skip-product`, `--incremental` (skip trackers matching previous run's manifest, and keep their outputs). Every run otherwise starts from a clean output directory -- `output/logs/` included, so no table sums two runs.

## Output Directory Structure

```text
output/
├── patient_data_raw/       # Raw extracted patient parquets (one per tracker)
├── patient_data_cleaned/   # Cleaned patient parquets (one per tracker)
├── product_data_raw/       # Raw extracted product parquets (one per tracker)
├── product_data_cleaned/   # Cleaned product parquets (one per tracker)
├── tables/                 # Final tables: patient_data_{static,monthly,annual}.parquet, product_data.parquet, clinic_data_static.parquet, table_logs.parquet, table_findings.parquet, tracker_metadata.parquet
└── logs/                   # Per-tracker log files (JSON)
```

`snapshot/` sits beside `output/` under the data root, not inside it. It holds the
golden-master baseline (`baseline.parquet`), the last check's digest
(`current.parquet`) and dated copies under `history/`. It is never committed --
this repository is public, and the digest would otherwise publish how many
patients each named clinic has. See the Golden-Master section of the README.

## Key Facts

- `clinic_id` = parent folder name of the tracker file
- Year detected from sheet names (`Jan24` → 2024) or filename
- Error sentinel values: numeric `999999`, string `"Undefined"`, date `"9999-09-09"`
- `report_finding()` is the only way to record a data-quality finding; it appends to the
  collector bound by `tracker_context()` and emits the same finding to the tracker's log
  stream. It raises outside a context rather than dropping the finding
- Two published artifacts, two jobs: `findings` (what is wrong with a workbook, for A4D
  staff) and `logs` (what the pipeline did, for a developer). `errors` is superseded
- Output stability is checked by `just snapshot-check`, which needs the tracker
  drive and so can never run in CI. Columns are hashed as multisets (BigQuery
  tables are unordered, and parallel workers reorder rows every run); each frame
  also carries a row-alignment fingerprint so one column cannot drift against the
  others unseen; run-time columns keep shape but no fingerprint; `table_logs` is
  excluded outright, since it records the run rather than the workbooks
- `reference_data/` holds the pipeline's shared configuration (synonyms, validation rules, provinces); changing it changes cleaning behaviour for every tracker

## Pipeline Status

- **Patient pipeline**: complete, deployed to production
- **Product pipeline**: complete, deployed to production
- **Tracker metadata table**: generated on every `create tables` / `run` run (MD5 + output-presence flags) and uploaded to BigQuery `tracker_metadata`.
- **Incremental processing**: shipped 2026-05-01 behind the `--incremental` CLI flag (opt-in) on `run patient`, `run product`, and the bare `run`. Skips trackers whose MD5 + completion state match the previous run's manifest (BigQuery → local parquet → empty fallback). Default behaviour unchanged. See the `a4d.state` module.
- **The R pipeline it replaced**: retired 2026-08-24. Recover its source with `git show r-archive-removed^:r-archive/R/<file>`; the migration's working papers are archived in [archive/](archive/README.md) and are not current guidance.
