# R to Python Migration Guide

Complete guide for migrating the A4D pipeline from R to Python.

---

## Quick Reference

**Status**: Phase 2 - Patient Extraction Complete ✅
**Next**: Export raw parquet + Product extraction
**Timeline**: 12-13 weeks total
**Current Branch**: `migration`
**Last Updated**: 2025-10-24

---

## Table of Contents

1. [Strategy & Decisions](#strategy--decisions)
2. [Technology Stack](#technology-stack)
3. [Architecture](#architecture)
4. [Key Migration Patterns](#key-migration-patterns)
5. [Phase Checklist](#phase-checklist)
6. [Code Examples](#code-examples)

---

## Strategy & Decisions

### Goals
1. **Output Compatibility** - Generate identical parquet files (or document differences)
2. **Performance** - 2-5x faster than R
3. **Incremental Processing** - Only reprocess changed trackers (hash-based)
4. **Error Transparency** - Same detailed error tracking as R

### Key Architectural Decisions

✅ **Per-Tracker Processing** - Process each tracker end-to-end, then aggregate
- Better for incremental updates
- Natural parallelization
- Failed tracker doesn't block others

✅ **No Orchestrator** - Simple Python + multiprocessing (not Prefect/doit/Airflow)
- DAG is simple: trackers → tables → BigQuery
- Multiprocessing sufficient for parallelization
- Less complexity, easier to maintain

✅ **BigQuery Metadata Table for State** - Not SQLite (containers are stateless)
- Query at pipeline start to get previous file hashes
- Only reprocess changed/new files
- Update metadata table at end
- Same table used for dashboards/analytics

✅ **Hybrid Error Logging** - Vectorized + row-level detail
- Try vectorized conversion (fast, handles 95%+ of data)
- Detect failures (nulls after conversion)
- Log only failed rows with patient_id, file_name, error details
- Export error logs as parquet (like other tables)

---

## Technology Stack

### Core (All from Astral where possible!)
- **uv** - Dependency management & Python version
- **ruff** - Linting & formatting
- **ty** - Type checking
- **polars** - DataFrames (10-100x faster than pandas)
- **duckdb** - Complex SQL operations
- **pydantic** - Settings & validation
- **pandera** - DataFrame schema validation
- **loguru** - Logging (JSON output)
- **pytest** - Testing

### GCP & Utilities
- **google-cloud-bigquery** - Replaces `bq` CLI
- **google-cloud-storage** - Replaces `gsutil` CLI
- **typer** - CLI interface
- **rich** - Beautiful console output

---

## Architecture

### Current R Pipeline (Batch per Step)
```
Step 1: ALL trackers → raw parquets
Step 2: ALL raw → ALL cleaned
Step 3: ALL cleaned → tables
```

**Problems**: Must reprocess everything, high memory, slow feedback

### New Python Pipeline (Per-Tracker)
```
For each changed tracker (in parallel):
  ├─ Extract → Clean → Export

Then aggregate all:
  ├─ All cleaned parquets → Final tables
  └─ Upload to BigQuery
```

**Benefits**: Incremental, parallel, lower memory, immediate feedback

### State Management Flow

```
1. Container starts (stateless, fresh)
2. Query BigQuery metadata table
   SELECT file_name, file_hash FROM tracker_metadata
3. Compare with current file hashes
4. Process only: new + changed + previously failed
5. Update metadata table (append new records)
6. Container shuts down (state persists in BigQuery)
```

### Error Logging Pattern

```python
# Try vectorized conversion
df = df.with_columns(pl.col("age").cast(pl.Int32, strict=False))

# Detect failures (became null but wasn't null before)
failed_rows = df.filter(conversion_failed)

# Log each failure with context
for row in failed_rows:
    error_collector.add_error(
        file_name=row["file_name"],
        patient_id=row["patient_id"],
        column="age",
        original_value=row["age_original"],
        error="Could not convert to Int32"
    )

# Replace with error value
df = df.with_columns(
    pl.when(conversion_failed).then(ERROR_VAL).otherwise(converted)
)
```

Result: Fast vectorization + complete error transparency

---

## Key Migration Patterns

### Configuration
```python
# R: config.yml → config::get()
# Python: .env → Pydantic Settings

from a4d.config import settings
print(settings.data_root)
print(settings.project_id)
```

### Logging
```python
# R: logInfo(log_to_json("msg", values=list(x=1)))
# Python: loguru

from loguru import logger

logger.info("Processing tracker", file="clinic_001.xlsx", rows=100)

# File-specific logging (like R's with_file_logger)
with file_logger("clinic_001_patient", output_root) as log:
    log.info("Processing patient data")
    log.error("Failed", error_code="critical_abort")
```

### DataFrames
```python
# R: df %>% filter(age > 18) %>% select(name, age)
# Python: Polars

df.filter(pl.col("age") > 18).select(["name", "age"])

# R: df %>% mutate(age = age + 1)
# Python:
df.with_columns((pl.col("age") + 1).alias("age"))
```

### Avoid rowwise() - Use Vectorized
```python
# R (slow):
# df %>% rowwise() %>% mutate(age_fixed = fix_age(age, dob, ...))

# Python (fast):
# Vectorized operations
df = df.with_columns([
    fix_age_vectorized(
        pl.col("age"),
        pl.col("dob"),
        pl.col("tracker_year")
    ).alias("age")
])

# OR if you must iterate (only for failures):
failed_rows = df.filter(needs_special_handling)
for row in failed_rows.iter_rows(named=True):
    # Handle edge case + log error
    pass
```

### Type Conversion with Error Tracking
```python
# R: convert_to(x, as.numeric, ERROR_VAL)
# Python:

df = safe_convert_column(
    df=df,
    column="age",
    target_type=pl.Int32,
    error_value=settings.error_val_numeric,
    error_collector=error_collector
)

# This function:
# 1. Tries vectorized conversion
# 2. Detects failures
# 3. Logs each failure with patient_id, file_name
# 4. Replaces with error value
```

### GCP Operations
```python
# R: system("gsutil cp ...")
# Python:
from google.cloud import storage
client = storage.Client()
bucket = client.bucket("a4dphase2_upload")
blob = bucket.blob("file.parquet")
blob.upload_from_filename("local_file.parquet")

# R: system("bq load ...")
# Python:
from google.cloud import bigquery
client = bigquery.Client()
job = client.load_table_from_dataframe(df, table_id)
job.result()
```

---

## Phase Checklist

### ✅ Phase 0: Foundation (DONE)
- [x] Create migration branch
- [x] Create a4d-python/ directory structure
- [x] Set up pyproject.toml with uv
- [x] Configure Astral toolchain (ruff, ty)
- [x] Add GitHub Actions CI
- [x] Create basic config.py

### Phase 1: Core Infrastructure (PARTIAL)
- [x] **reference/synonyms.py** - Column name mapping ✅
  - Load YAML files (reuse from reference_data/)
  - Create reverse mapping dict
  - `rename_columns()` method with strict mode
  - Comprehensive test coverage

- [x] **reference/provinces.py** - Province validation ✅
  - Load allowed provinces YAML
  - Case-insensitive validation
  - Country mapping

- [x] **reference/loaders.py** - YAML loading utilities ✅
  - Find reference_data directory
  - Load YAML with validation

- [ ] **logging.py** - loguru setup with JSON output
  - Console handler (pretty, colored)
  - File handler (JSON for BigQuery upload)
  - `file_logger()` context manager

- [ ] **clean/converters.py** - Type conversion with error tracking
  - `ErrorCollector` class
  - `safe_convert_column()` function
  - Vectorized + detailed error logging

- [ ] **schemas/validation.py** - YAML-based validation
  - Load data_cleaning.yaml
  - Apply allowed_values rules
  - Integrate with Pandera schemas

- [ ] **gcp/storage.py** - GCS operations
  - `download_bucket()`
  - `upload_directory()`

- [ ] **gcp/bigquery.py** - BigQuery operations
  - `ingest_table()` with parquet

- [ ] **state/bigquery_state.py** - State management
  - Query previous file hashes
  - `get_files_to_process()` - incremental logic
  - `update_metadata()` - append new records

- [ ] **utils/paths.py** - Path utilities

### Phase 2: Script 1 - Extraction (IN PROGRESS) ⚡
- [x] **extract/patient.py** - COMPLETED ✅
  - [x] Read Excel with openpyxl (read-only, single-pass optimization)
  - [x] Find all month sheets automatically
  - [x] Extract tracker year from sheet names or filename
  - [x] Read and merge two-row headers (with horizontal fill-forward)
  - [x] Handle merged cells creating duplicate columns (R-compatible merge with commas)
  - [x] Apply synonym mapping with `ColumnMapper`
  - [x] Extract from all month sheets with metadata (sheet_name, tracker_month, tracker_year, file_name)
  - [x] Combine sheets with `diagonal_relaxed` (handles type mismatches)
  - [x] Filter invalid rows (null patient_id, or "0"/"0" combinations)
  - [x] 25 comprehensive tests (110 total test suite)
  - [x] 91% code coverage for patient.py
  - [ ] Export raw parquet (next step)

- [ ] **extract/product.py** - TODO
  - Same pattern as patient

- [x] **Test on sample trackers** - DONE
  - Tested with 2024, 2019, 2018 trackers
  - Handles format variations across years

- [ ] **Compare outputs with R pipeline** - TODO
  - Need to run both pipelines and compare parquet outputs

### Phase 3: Script 2 - Cleaning (Week 5-7)
- [ ] **clean/patient.py**
  - Handle legacy formats (extract dates from measurements)
  - Split blood pressure
  - Detect exceeds indicators
  - Type conversion with error tracking
  - Apply fixes (height, weight, BMI, age)
  - YAML validation

- [ ] **clean/product.py**
  - Similar pattern

- [ ] **Test on sample data**
- [ ] **Compare outputs with R**
- [ ] **Compare error logs** (counts, patient_ids)

### Phase 4: Script 3 - Tables (Week 7-9)
- [ ] **tables/patient.py**
  - `create_table_patient_data_static()`
  - `create_table_patient_data_monthly()` - with DuckDB for changes
  - `create_table_patient_data_annual()`

- [ ] **tables/product.py**
  - `create_table_product_data()`

- [ ] **tables/clinic.py**
  - `create_table_clinic_static_data()`

- [ ] **Logs table** - Aggregate all error parquets

- [ ] **Compare final tables with R**

### Phase 5: Pipeline Integration (Week 9-10)
- [ ] **pipeline/tracker_pipeline.py**
  - `TrackerPipeline.process()` - end-to-end per tracker

- [ ] **scripts/run_pipeline.py**
  - Query BigQuery state
  - Parallel processing with ProcessPoolExecutor
  - Create final tables
  - Upload to BigQuery
  - Update metadata table

- [ ] **Test end-to-end locally**

### Phase 6: GCP Deployment (Week 10-11)
- [ ] Finalize Dockerfile
- [ ] Test GCS upload/download
- [ ] Deploy to Cloud Run (test)
- [ ] Test with Cloud Scheduler trigger

### Phase 7: Validation (Week 11-12)
- [ ] Run both R and Python pipelines on production data
- [ ] Automated comparison of all outputs
- [ ] Performance benchmarking
- [ ] Fix discovered bugs

### Phase 8: Cutover (Week 12-13)
- [ ] Final validation
- [ ] Deploy to production
- [ ] Monitor first run
- [ ] Deprecate R pipeline

---

## Code Examples

### 1. Configuration (src/a4d/config.py)

Already implemented ✅

### 2. Logging Setup (src/a4d/logging.py)

```python
from loguru import logger
from pathlib import Path
import sys

def setup_logging(log_dir: Path, log_name: str):
    """Configure loguru for BigQuery-compatible JSON logs."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"main_{log_name}.log"

    logger.remove()  # Remove default

    # Console (pretty, colored)
    logger.add(sys.stdout, level="INFO", colorize=True)

    # File (JSON for BigQuery)
    logger.add(
        log_file,
        serialize=True,  # JSON output
        level="DEBUG",
        rotation="100 MB",
    )

from contextlib import contextmanager

@contextmanager
def file_logger(file_name: str, output_root: Path):
    """File-specific logging (like R's with_file_logger)."""
    log_file = output_root / "logs" / f"{file_name}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler_id = logger.add(log_file, serialize=True)
    bound_logger = logger.bind(file_name=file_name)

    try:
        yield bound_logger
    except Exception:
        bound_logger.exception("Processing failed", error_code="critical_abort")
        raise
    finally:
        logger.remove(handler_id)
```

### 3. Synonym Mapper (src/a4d/synonyms/mapper.py)

```python
import yaml
from pathlib import Path
import polars as pl

class SynonymMapper:
    def __init__(self, synonym_file: Path):
        with open(synonym_file) as f:
            synonyms = yaml.safe_load(f)

        # Reverse mapping: synonym -> standard
        self._mapping = {}
        for standard, variants in synonyms.items():
            if isinstance(variants, list):
                for variant in variants:
                    self._mapping[variant.lower()] = standard
            else:
                self._mapping[variants.lower()] = standard

    def rename_dataframe(self, df: pl.DataFrame) -> pl.DataFrame:
        """Rename columns using synonym mapping."""
        mapping = {col: self._mapping.get(col.lower(), col) for col in df.columns}
        return df.rename(mapping)

# Cache mappers
from functools import lru_cache

@lru_cache(maxsize=2)
def get_synonym_mapper(data_type: str) -> SynonymMapper:
    file = Path(f"../reference_data/synonyms/synonyms_{data_type}.yaml")
    return SynonymMapper(file)
```

### 4. Error Tracking Converter (src/a4d/clean/converters.py)

```python
from dataclasses import dataclass
import polars as pl

@dataclass
class ConversionError:
    file_name: str
    patient_id: str
    column: str
    original_value: any
    error_message: str

class ErrorCollector:
    def __init__(self):
        self.errors = []

    def add_error(self, file_name, patient_id, column, original_value, error_message):
        self.errors.append(ConversionError(
            file_name, patient_id, column, str(original_value), error_message
        ))

    def to_dataframe(self) -> pl.DataFrame:
        if not self.errors:
            return pl.DataFrame()
        return pl.DataFrame([e.__dict__ for e in self.errors])

def safe_convert_column(
    df: pl.DataFrame,
    column: str,
    target_type: pl.DataType,
    error_value: any,
    error_collector: ErrorCollector
) -> pl.DataFrame:
    """Vectorized conversion with row-level error tracking."""

    # Store original
    df = df.with_columns(pl.col(column).alias(f"_orig_{column}"))

    # Try vectorized conversion
    df = df.with_columns(
        pl.col(column).cast(target_type, strict=False).alias(f"_conv_{column}")
    )

    # Detect failures
    failed = df.filter(
        pl.col(f"_conv_{column}").is_null() &
        pl.col(f"_orig_{column}").is_not_null()
    )

    # Log each failure
    for row in failed.iter_rows(named=True):
        error_collector.add_error(
            file_name=row.get("file_name", "unknown"),
            patient_id=row.get("patient_id", "unknown"),
            column=column,
            original_value=row[f"_orig_{column}"],
            error_message=f"Could not convert to {target_type}"
        )

    # Replace failures with error value
    df = df.with_columns(
        pl.when(pl.col(f"_conv_{column}").is_null())
        .then(pl.lit(error_value))
        .otherwise(pl.col(f"_conv_{column}"))
        .alias(column)
    )

    return df.drop([f"_orig_{column}", f"_conv_{column}"])
```

### 5. State Manager (src/a4d/state/bigquery_state.py)

```python
from google.cloud import bigquery
import polars as pl
import hashlib
from pathlib import Path

class BigQueryStateManager:
    def __init__(self, project_id: str, dataset: str):
        self.client = bigquery.Client(project=project_id)
        self.table_id = f"{project_id}.{dataset}.tracker_metadata"

    def get_file_hash(self, file_path: Path) -> str:
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_previous_state(self) -> pl.DataFrame:
        """Query BigQuery for previous file hashes."""
        query = f"""
        SELECT file_name, file_hash, status
        FROM `{self.table_id}`
        WHERE last_processed = (
            SELECT MAX(last_processed)
            FROM `{self.table_id}` AS t2
            WHERE t2.file_name = {self.table_id}.file_name
        )
        """
        df_pandas = self.client.query(query).to_dataframe()
        return pl.from_pandas(df_pandas) if len(df_pandas) > 0 else pl.DataFrame()

    def get_files_to_process(self, tracker_files: list[Path], force=False) -> list[Path]:
        """Determine which files need processing (incremental)."""
        if force:
            return tracker_files

        previous = self.get_previous_state()
        if len(previous) == 0:
            return tracker_files

        prev_lookup = {
            row["file_name"]: (row["file_hash"], row["status"])
            for row in previous.iter_rows(named=True)
        }

        to_process = []
        for file in tracker_files:
            current_hash = self.get_file_hash(file)

            if file.name not in prev_lookup:
                to_process.append(file)  # New
            else:
                prev_hash, status = prev_lookup[file.name]
                if current_hash != prev_hash or status == "failed":
                    to_process.append(file)  # Changed or failed

        return to_process
```

---

## Reference Data (Reusable)

All YAML files in `reference_data/` can be used as-is:
- ✅ `synonyms/synonyms_patient.yaml`
- ✅ `synonyms/synonyms_product.yaml`
- ✅ `data_cleaning.yaml`
- ✅ `provinces/allowed_provinces.yaml`

No migration needed - just reference from Python code.

---

## Success Criteria

### Correctness
- [ ] All final tables match R output (or differences documented)
- [ ] Error counts match R
- [ ] Same patient_ids flagged

### Performance
- [ ] 2-5x faster than R
- [ ] Incremental runs only process changed files
- [ ] Memory usage <8GB

### Code Quality
- [ ] Test coverage >80%
- [ ] ruff linting passes
- [ ] ty type checking passes

### Deployment
- [ ] Runs in Cloud Run
- [ ] Incremental processing works
- [ ] Monitoring set up

---

## Notes for Implementation

1. **Start with infrastructure** - Don't jump to extraction yet
2. **Test continuously** - Write tests alongside code
3. **Compare with R** - After each phase, validate outputs match
4. **Use existing R code as reference** - Read the R scripts to understand logic
5. **Ask questions** - Migration docs are guides, not absolute rules
6. **Document differences** - If output differs from R, document why

---

## Recent Progress (2025-10-24)

### ✅ Completed: Patient Data Extraction
- **Module**: `src/a4d/extract/patient.py` (180 lines, 91% coverage)
- **Tests**: 25 tests in `tests/test_extract/test_patient.py` (152 lines)
- **Key Features**:
  - Single-pass read-only Excel loading for optimal performance
  - Automatic month sheet detection and year extraction
  - Two-row header merging with horizontal fill-forward logic
  - **R-compatible duplicate column handling**: Merges values with commas (like `tidyr::unite()`)
  - Synonym-based column harmonization
  - Multi-sheet extraction with metadata (sheet_name, tracker_month, tracker_year, file_name)
  - Type-safe concatenation with `diagonal_relaxed`
  - Intelligent row filtering (removes invalid patient_id patterns)

### 🔑 Key Learnings
1. **Always verify against R implementation** - Initially implemented incorrect duplicate column handling (renaming) instead of correct approach (merging values)
2. **Polars constraints** - Cannot have duplicate column names, must handle before DataFrame creation
3. **Type mismatches** - Use `diagonal_relaxed` when concatenating DataFrames with schema differences
4. **Simplicity wins** - Refactored complex nested loops to elegant dict-based approach (26% code reduction)

### 📝 Next Steps
1. Add parquet export to `extract/patient.py`
2. Implement `extract/product.py` (similar pattern)
3. Compare outputs with R pipeline (run both and validate parity)
4. Move to Phase 3: Cleaning module

---

## Questions During Migration

1. How to handle date parsing edge cases?
2. Exact numeric precision for comparisons?
3. Memory optimization for large files?
4. Optimal parallel workers for Cloud Run?

→ These will be answered during implementation
