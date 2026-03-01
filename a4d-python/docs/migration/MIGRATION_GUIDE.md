# R to Python Migration Guide

Reference for the A4D pipeline migration from R to Python.

**Status**: Phases 0–7 complete. Patient pipeline production-ready. Product pipeline not yet started.
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
├── extract/patient.py     # Excel → raw parquet
├── clean/
│   ├── patient.py         # Main cleaning pipeline
│   ├── schema.py          # 83-column meta schema
│   ├── converters.py      # Safe type conversion + ErrorCollector
│   ├── validators.py      # Case-insensitive allowed-values
│   ├── transformers.py    # Explicit transformations
│   └── date_parser.py     # Flexible date parsing
├── tables/
│   ├── patient.py         # static/monthly/annual aggregation
│   └── logs.py            # Error log aggregation
├── pipeline/
│   ├── patient.py         # Orchestration + parallel workers
│   ├── tracker.py         # Per-tracker execution
│   └── models.py          # Result dataclasses
├── gcp/
│   ├── storage.py         # GCS operations
│   └── bigquery.py        # BigQuery load
├── reference/
│   ├── synonyms.py        # Column name mapping (YAML)
│   ├── provinces.py       # Allowed province validation
│   └── loaders.py         # YAML loading utilities
├── state/                 # State management (exists, not yet wired up)
├── config.py              # Pydantic settings from A4D_* env vars
├── logging.py             # loguru setup
├── errors.py              # Shared error types
└── cli.py                 # Typer CLI (6 commands)
```

### State Management (Designed, Not Yet Active)

```
1. Container starts (stateless, fresh)
2. Query BigQuery metadata table
   SELECT file_name, file_hash FROM tracker_metadata
3. Compare with current file hashes
4. Process only: new + changed + previously failed
5. Update metadata table (append new records)
6. Container shuts down (state persists in BigQuery)
```

Currently: pipeline processes all trackers found in `data_root`. Incremental logic exists in `state/` but is not wired into `pipeline/patient.py` yet.

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

---

## Open Items

### Phase 8: First GCP Production Run

- Run `run-pipeline` against production GCS bucket (patient data)
- Validate BigQuery table outputs match expected counts/schema
- Compare dashboard reports with R pipeline baseline
- Fix any issues discovered during first real run

### Phase 9: Product Pipeline

- `extract/product.py` — same pattern as patient extraction
- `clean/product.py` — same pattern as patient cleaning
- `tables/product.py` — product aggregation tables
- Validate against R product pipeline outputs

### State Management (Incremental Processing)

- `state/` module exists with BigQuery state design
- Wire into `pipeline/patient.py` so only changed/new trackers are processed
- Required before production scheduling (Cloud Run + Cloud Scheduler)

---

## Reference Data

All YAML files in `reference_data/` are shared with the R pipeline — do not modify without testing both:
- `reference_data/synonyms/synonyms_patient.yaml`
- `reference_data/synonyms/synonyms_product.yaml`
- `reference_data/data_cleaning.yaml`
- `reference_data/provinces/allowed_provinces.yaml`
