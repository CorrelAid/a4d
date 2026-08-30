# A4D Data Processing Pipeline (Python)

Python implementation of the A4D medical tracker data processing pipeline.

## Status

Production. Both arms (patient and product) run as one orchestrated pipeline on
Cloud Run against the A4D GCS bucket, landing in BigQuery.

This replaced an earlier R implementation, which was retired on 2026-08-24. The
record of that migration is archived in [docs/archive/](docs/archive/); nothing
in it is current guidance.

## Features

- ✅ **Dual Pipeline Arms** - Patient and product trackers processed in one run
- ✅ **Incremental Processing** - Skip trackers whose MD5 + completion state match the previous run's manifest
- ✅ **Parallel Execution** - Process multiple trackers concurrently
- ✅ **Stateless GCP Deployment** - Uses BigQuery for state management
- ✅ **Comprehensive Error Tracking** - Detailed error logs per patient/tracker
- ✅ **High Performance** - Built on Polars (10-100x faster than pandas)

## Quick Start

### Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install just (optional, for convenient commands)
# macOS: brew install just
# Other: https://github.com/casey/just

# Install dependencies
just sync
# or: uv sync --all-extras
```

### Configuration

Create a `.env` file:

```bash
A4D_ENVIRONMENT=development
A4D_DATA_ROOT=/path/to/tracker/files
A4D_PROJECT_ID=a4dphase2
A4D_DATASET=tracker
A4D_DOWNLOAD_BUCKET=a4dphase2_upload
A4D_UPLOAD_BUCKET=a4dphase2_output
```

### Running the Pipeline

```bash
# Full end-to-end pipeline (Drive + GCS download → patient + product → GCS + BigQuery upload)
just run
# or: uv run a4d run

# Common `a4d run` flags
just run --workers 8
just run --skip-upload          # Local testing: process but don't upload
just run --skip-download        # Reuse files already in data_root
just run --skip-drive-download  # Skip clinic_data.xlsx refresh from Google Drive
just run --skip-product         # Patient-only run
just run --skip-patient         # Product-only run (mutually exclusive with --skip-product)
just run --incremental          # Skip unchanged trackers (MD5 + completion match), keeping their outputs
just run --force                # Wipe prior local outputs even under --incremental

# Single-arm runs (no GCS download/upload)
just run-local                  # Patient extract + clean + tables
just run-local-product          # Product extract + clean + tables
just run-file path/to/tracker.xlsx          # Single patient tracker
just run-file-product path/to/tracker.xlsx  # Single product tracker
```

## Architecture

```
`a4d run` flow:
0. Download reference data (clinic_data.xlsx) from Google Drive
1. Download tracker files from GCS
2-3. Patient arm: extract → clean → tables (static, monthly, annual)
3b.  Clinic static table from clinic_data.xlsx
3c.  Product arm: extract → clean → product_data table
3d.  Tracker metadata table (MD5 + per-tracker output presence)
3e.  Product ↔ patient link validation (logging-only)
4.   Upload tables/ and logs/ to GCS under YYYY/MM/DD/HHMMSS/
5.   Ingest tables into BigQuery (WRITE_TRUNCATE)
```

Both arms share the same tracker queue. With `--incremental`, the queue is filtered once against the previous run's manifest so both arms see the same set.

Output tables loaded into BigQuery:

- `patient_data_static`, `patient_data_monthly`, `patient_data_annual`
- `product_data`
- `clinic_data_static`
- `tracker_metadata`
- `logs`

## Project Structure

```
a4d/
├── src/a4d/           # Main package
│   ├── cli.py         # Typer CLI (run/create/upload/download command groups)
│   ├── config.py      # Pydantic settings (A4D_* env vars)
│   ├── logging.py     # loguru configuration
│   ├── extract/       # Sheet extraction (patient.py, product.py, wide_format.py)
│   ├── clean/         # Cleaning + schemas (patient.py, product.py, schema*.py)
│   ├── pipeline/      # Per-arm orchestration (patient.py, product.py, tracker.py)
│   ├── tables/        # Aggregation into final parquets (patient, product, clinic, metadata, logs)
│   ├── validate/      # Source-vs-output reconciliation (patient + product)
│   ├── gcp/           # BigQuery, GCS, Drive integration
│   ├── reference/     # Reference data loaders (synonyms, validation rules, provinces)
│   ├── state/         # Manifest + incremental filtering
│   └── utils/         # Shared utilities
├── reference_data/    # Shared YAML configs + clinic_data.xlsx
├── tests/             # Test suite
├── scripts/           # Utility scripts
├── docs/              # Migration + feature docs
├── justfile           # Development commands
└── pyproject.toml     # Dependencies
```

## Development

### Common Commands

```bash
# Show all available commands
just

# Run exactly what CI runs (lint, format, types, tests, coverage floor)
just ci

# Format code
just format

# Lint code
just lint

# Auto-fix linting issues
just fix

# Type checking with ty
just check

# Clean build artifacts
just clean
```

### Running Tests

There are two test commands, and the split is deliberate:

```bash
# The check suite -- exactly the selection CI runs, with coverage
just test

# The drive-dependent tests -- run these when the tracker USB drive is mounted.
# CI cannot run them at all, so they are never part of `just ci`.
just test-integration

# Development loop: same selection as `just test`, no coverage, stop at first failure
just test-fast

# A single file
uv run pytest tests/test_extract/test_patient.py
```

### Code Quality

`just ci` runs the checks in CI's own order, and the CI workflow
(`.github/workflows/python-ci.yml`) invokes these same recipes step by step --
so the local set and CI are one definition and cannot drift apart:

```bash
just ci            # everything below, in order

just lint          # ruff check .
just format-check  # ruff format --check .
just check         # ty check src/
just test          # pytest, CI's selection, with coverage
just cov-floor     # product pipeline code must stay 85% covered

just format        # rewrite files to match the formatter
just fix           # auto-fix lint findings
```

### Pre-push Hook

Nothing forces `just ci` to be run, and forgetting it is how CI once stayed red
for four days. Install the hook so a push runs the checks first:

```bash
just hooks
```

It copies `scripts/hooks/pre-push` into `.git/hooks/`, adding roughly 40
seconds to a push. Bypass it for a single push with `git push --no-verify`.

### Docker

```bash
# Build Docker image (tagged :latest and :<git-sha>)
just docker-build

# Smoke-test the image (CLI reachable inside the container)
just docker-smoke

# Push both tags to Artifact Registry
just docker-push

# Or manually (build from the repo root; the image writes under A4D_DATA_ROOT):
docker build --platform=linux/amd64 -t a4d-pipeline:latest .
docker run --rm --env-file .env -v "$(pwd)/data:/workspace/data" a4d-pipeline:latest
```

### Other Commands

```bash
# Update dependencies
just update

# Show project info
just info
```

## Technology Stack

### Astral Toolchain

- **uv** - Fast dependency management
- **ruff** - Linting and formatting
- **ty** - Type checking

### Data Processing

- **Polars** - Fast dataframe operations (10-100x faster than pandas)
- **DuckDB** - Complex SQL aggregations
- **Pydantic** - Type-safe configuration
- **Pandera** - DataFrame validation

### Infrastructure

- **loguru** - Structured JSON logging
- **Google Cloud SDK** - BigQuery & GCS integration
- **pytest** - Testing framework
- **just** - Command runner for development

## History

This pipeline replaced an R implementation, retired 2026-08-24. What the
rewrite gained:

- Patient and product trackers in a single orchestrated run
- Incremental processing (only changed files)
- Row-level error tracking, published as its own BigQuery table
- Single Docker container, deployed to Cloud Run

The migration was verified cell-by-cell against the old pipeline's frozen
output over 254 trackers before it was retired. Those working papers are in
[docs/archive/](docs/archive/), frozen and not maintained.

## License

MIT
