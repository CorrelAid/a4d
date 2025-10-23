# CLAUDE.md

## Project Overview

**Python implementation** of the A4D medical tracker data processing pipeline (migrating from R).

This project processes, cleans, and ingests medical tracker data (Excel files) for the CorrelAid A4D project.
It extracts patient and product data from Excel trackers, validates and cleans the data, and creates structured tables for ingestion into Google BigQuery.

**Migration Status**: Phase 2 - Patient Extraction Complete ✅
**See**: [Migration Guide](migration/MIGRATION_GUIDE.md) for complete migration details
**Last Updated**: 2025-10-24

## Package Structure

Modern Python package using **uv** for dependency management and Astral's toolchain. Pipeline architecture:

1. **Extract** - Read Excel trackers, apply synonym mapping
2. **Clean** - Validate, type conversion with error tracking
3. **Tables** - Aggregate into final BigQuery tables
4. **State** - BigQuery-based incremental processing

## Essential Commands

### Initial Setup

```bash
# Install dependencies
uv sync

# Install development dependencies
uv sync --all-extras

# Create .env file (copy from .env.example)
cp .env.example .env
# Edit .env with your paths and GCP settings
```

### Development Workflow

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov

# Linting
uv run ruff check .

# Formatting
uv run ruff format .

# Type checking
uv run ty check src/

# All checks
uv run ruff check . && uv run ruff format . && uv run ty check src/ && uv run pytest
```

### Running the Pipeline

```bash
# Full pipeline
uv run python scripts/run_pipeline.py

# Options
uv run python scripts/run_pipeline.py --max-workers 8  # Parallel processing
uv run python scripts/run_pipeline.py --force           # Reprocess all files
uv run python scripts/run_pipeline.py --skip-upload     # Local testing
```

### Configuration

Edit `.env` file:

```bash
A4D_DATA_ROOT=/path/to/tracker/files
A4D_PROJECT_ID=a4dphase2
A4D_DATASET=tracker
A4D_DOWNLOAD_BUCKET=a4dphase2_upload
A4D_UPLOAD_BUCKET=a4dphase2_output
```

## Architecture

### Data Flow

```text
Query BigQuery → Identify changed trackers
       ↓
For each tracker (parallel):
  Extract → Clean → Validate → Export parquet
       ↓
Aggregate all parquets → Final tables
       ↓
Upload to BigQuery + Update metadata
```

### Key Directories

- **src/a4d/**: Main package
  - `config.py`: Pydantic settings (replaces config.yml)
  - `extract/`: Excel reading, synonym mapping (Script 1)
  - `clean/`: Type conversion, validation, error tracking (Script 2)
  - `tables/`: Final table creation (Script 3)
  - `gcp/`: BigQuery & GCS integration
  - `state/`: BigQuery-based state management
  - `pipeline/`: Per-tracker orchestration

- **tests/**: Test suite with pytest

- **scripts/**: CLI entry points

- **../reference_data/**: Shared with R (YAML configs)

### Key Features

**Incremental Processing**:
- Query BigQuery metadata table for previous file hashes
- Only process new/changed/failed files
- Update metadata after processing

**Error Tracking**:
- Vectorized conversions (fast)
- Row-level error logging for failures
- Export error details as parquet
- Each error includes: file_name, patient_id, column, original_value

**Technology Stack**:
- **Polars** - Fast DataFrames
- **loguru** - Structured JSON logging
- **Pydantic** - Type-safe configuration
- **Astral tools** - uv, ruff, ty

## Output Tables

Same as R pipeline:
- `patient_data_monthly` - Monthly observations
- `patient_data_annual` - Annual data
- `patient_data_static` - Static attributes
- `patient_data_hba1c` - Longitudinal HbA1c
- `product_data` - Product distribution
- `clinic_data_static` - Clinic info
- `logs` - Error logs
- `tracker_metadata` - Processing state

## Migration Notes

When migrating R code:
1. Check [Migration Guide](migration/MIGRATION_GUIDE.md) for patterns
2. R's `rowwise()` → Python vectorized operations
3. Error tracking via `ErrorCollector` class
4. Read R scripts to understand logic, then apply Python patterns
5. Compare outputs with R pipeline after each phase
6. Do not migrate blindly – adapt to Pythonic idioms and performance best practices
