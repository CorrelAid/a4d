# R to Python Migration Guide

Reference for the A4D pipeline migration from R to Python.

**Status**: Phases 0–9 complete. Patient pipeline production-ready. Product pipeline merged into `src/a4d/` on 2026-04-23.
**Branch**: `migration`

---

## Table of Contents

1. [Strategy & Decisions](#strategy--decisions)
2. [Technology Stack](#technology-stack)
3. [Architecture](#architecture)
4. [Key Code Patterns](#key-code-patterns)
5. [Open Items](#open-items)

---

## Strategy & Decisions

### Goals
1. **Output Compatibility** — Generate equivalent parquet files (differences documented)
2. **Performance** — 2-5x faster than R
3. **Incremental Processing** — Only reprocess changed trackers (hash-based)
4. **Error Transparency** — Detailed per-row error tracking

### Key Architectural Decisions

**Per-Tracker Processing** — Process each tracker end-to-end, then aggregate
- Better for incremental updates; natural parallelization; failed tracker doesn't block others

**No Orchestrator** — Simple Python + multiprocessing (not Prefect/doit/Airflow)
- DAG is simple: trackers → tables → BigQuery; less complexity, easier to maintain

**BigQuery Metadata Table for State** — Not SQLite (containers are stateless)
- Query at pipeline start to get previous file hashes; only reprocess changed/new files; same table used for dashboards

**Hybrid Error Logging** — Vectorized + row-level detail
- Try vectorized conversion (handles 95%+ of data); detect failures; log only failed rows with patient_id, file_name, error details; export error logs as parquet

---

## Technology Stack

- **uv** — Dependency management & Python version
- **ruff** — Linting & formatting
- **polars** — DataFrames (10-100x faster than pandas)
- **duckdb** — Complex SQL operations
- **pydantic** — Settings & validation
- **loguru** — Logging (JSON output)
- **pytest** — Testing
- **google-cloud-bigquery** — Replaces `bq` CLI
- **google-cloud-storage** — Replaces `gsutil` CLI
- **typer + rich** — CLI interface

---

## Architecture

### Data Flow

```
Excel Trackers (GCS)
       |
       v
download-trackers          # GCS → local data_root/
       |
       v
process-patient            # For each tracker (parallel):
  ├─ extract/patient.py    #   Excel → patient_data_raw/*.parquet
  └─ clean/patient.py      #   raw → patient_data_cleaned/*.parquet
       |
       v
create-tables              # All cleaned parquets →
  ├─ tables/patient.py     #   tables/static.parquet
  |                        #   tables/monthly.parquet
  |                        #   tables/annual.parquet
  └─ tables/logs.py        #   tables/logs.parquet
       |
       v
upload-output              # local output/ → GCS
upload-tables              # tables/*.parquet → BigQuery
```

### Module Structure

```
src/a4d/
├── extract/
│   ├── patient.py         # Patient: Excel → raw parquet
│   ├── product.py         # Product: Excel month sheets → raw parquet
│   └── wide_format.py     # Mandalay wide-format handlers (column/cell)
├── clean/
│   ├── patient.py         # Patient cleaning pipeline
│   ├── product.py         # Product cleaning pipeline (R steps 2.0-2.21)
│   ├── schema.py          # 83-column patient schema
│   ├── schema_product.py  # 19-column product schema
│   ├── converters.py      # Safe type conversion + ErrorCollector
│   ├── validators.py      # Case-insensitive allowed-values
│   ├── transformers.py    # Explicit transformations
│   └── date_parser.py     # Flexible date parsing
├── tables/
│   ├── patient.py         # static/monthly/annual aggregation
│   ├── product.py         # product_data aggregation
│   ├── clinic.py          # clinic static table
│   └── logs.py            # Error log aggregation
├── pipeline/
│   ├── patient.py         # Patient orchestration + parallel workers
│   ├── product.py         # Product orchestration (mirrors patient)
│   ├── tracker.py         # Per-tracker execution (patient + product)
│   └── models.py          # Result dataclasses
├── gcp/
│   ├── storage.py         # GCS operations
│   ├── drive.py           # Google Drive (clinic_data.xlsx)
│   └── bigquery.py        # BigQuery load
├── reference/
│   ├── synonyms.py        # Column name mapping (YAML)
│   ├── products.py        # Stock_Summary product reference loader
│   ├── provinces.py       # Allowed province validation
│   └── loaders.py         # YAML loading utilities
├── state/                 # State management (exists, not yet wired up)
├── config.py              # Pydantic settings from A4D_* env vars
├── logging.py             # loguru setup
├── errors.py              # Shared error types
└── cli.py                 # Typer CLI (patient + product commands, run-pipeline)
```

### State Management (Incremental Processing)

```
1. Container starts (stateless, fresh)
2. Query BigQuery metadata table
   SELECT file_name, clinic_code, md5, complete FROM tracker_metadata
3. Compare with current file MD5s
4. Process only: new + changed + previously incomplete
5. Re-publish metadata table (full replace) at end of run
6. Container shuts down (state persists in BigQuery)
```

Wired up via the `a4d.state` module ([src/a4d/state/](../../src/a4d/state/)) and exposed
through the `--incremental` CLI flag on `process-patient`, `process-product`, and
`run-pipeline`. Source precedence is BigQuery → local
`output_root/tables/tracker_metadata.parquet` → empty manifest, so local devs
without `gcloud auth` get the local-parquet fallback automatically.

The flag is **opt-in**: default behaviour is unchanged (process every tracker
found in `data_root`). Flipping the default to incremental is a separate
decision after a soak window.

---

## Key Code Patterns

### Configuration
```python
from a4d.config import settings
settings.data_root      # Path to tracker files
settings.project_id     # GCP project
settings.output_root    # Local output directory
```

### Error Tracking
```python
# ErrorCollector accumulates failures without raising
error_collector = ErrorCollector()

df = safe_convert_column(
    df=df,
    column="age",
    target_type=pl.Int32,
    error_value=settings.error_val_numeric,
    error_collector=error_collector,
)
# Errors exported as parquet → aggregated into logs table
```

### Vectorized Conversion Pattern
```python
# Try vectorized conversion
df = df.with_columns(pl.col("age").cast(pl.Int32, strict=False))

# Detect failures (null after conversion but wasn't null before)
failed_rows = df.filter(conversion_failed)

# Log each failure; replace with error value
```

### Avoiding R's rowwise() Pattern
```python
# R (slow): df %>% rowwise() %>% mutate(age_fixed = fix_age(age, dob, ...))

# Python (fast): vectorized
df = df.with_columns([
    fix_age_vectorized(pl.col("age"), pl.col("dob"), pl.col("tracker_year")).alias("age")
])

# Only iterate for genuine edge cases (log + replace)
```

### DataFrames (R → Python)
```python
# R: df %>% filter(age > 18) %>% select(name, age)
df.filter(pl.col("age") > 18).select(["name", "age"])

# R: df %>% mutate(age = age + 1)
df.with_columns((pl.col("age") + 1).alias("age"))
```

### GCP Operations
```python
# R: system("gsutil cp ...")
from google.cloud import storage
bucket = storage.Client().bucket("a4dphase2_upload")
bucket.blob("file.parquet").upload_from_filename("local_file.parquet")

# R: system("bq load ...")
from google.cloud import bigquery
job = bigquery.Client().load_table_from_dataframe(df, table_id)
job.result()
```

### Logging
```python
from loguru import logger
logger.info("Processing tracker", file="clinic_001.xlsx", rows=100)

# File-specific logging (like R's with_file_logger)
with file_logger("clinic_001_patient", output_root) as log:
    log.info("Processing patient data")
```

---

## Completed Phases

| Phase | Description |
|-------|-------------|
| 0 | Foundation: repo structure, uv, ruff, CI |
| 1 | Core infrastructure: reference, logging, config, ErrorCollector |
| 2 | Extraction: `extract/patient.py` (28 tests, 88% coverage) |
| 3 | Cleaning: `clean/patient.py` (83-column schema, full validation) |
| 4 | Tables: `tables/patient.py` (static, monthly, annual, logs) |
| 5 | Pipeline integration: `pipeline/patient.py` + parallel processing |
| 6 | GCP: `gcp/storage.py`, `gcp/bigquery.py`, CLI commands |
| 7 | Validation: 174 trackers compared, 8 bugs fixed, production verdict |
| 9 | Product pipeline: merged WIP product modules into `src/a4d/`; `run-pipeline` runs both arms. |

---

## Open Items

### Phase 8: First GCP Production Run

- Run `run-pipeline` against production GCS bucket (patient data)
- Validate BigQuery table outputs match expected counts/schema
- Compare dashboard reports with R pipeline baseline
- Fix any issues discovered during first real run

### Production Scheduling

Cloud Run + Cloud Scheduler wiring (cron, image build, deploy manifest). The
state module shipped behind the `--incremental` CLI flag — see the
[State Management](#state-management-incremental-processing) section above.
The default behaviour remains "process every tracker"; flipping the default to
incremental is a separate decision after a soak window.

---

## Reference Data

All YAML files in `reference_data/` are shared with the R pipeline — do not modify without testing both:
- `reference_data/synonyms/synonyms_patient.yaml`
- `reference_data/synonyms/synonyms_product.yaml`
- `reference_data/data_cleaning.yaml`
- `reference_data/provinces/allowed_provinces.yaml`
