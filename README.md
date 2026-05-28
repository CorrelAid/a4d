# A4D Data Processing Pipeline (Python)

Python implementation of the A4D medical tracker data processing pipeline.

## Migration Status

🚧 **Active Development** - Migrating from R to Python

See the [Migration Guide](docs/migration/MIGRATION_GUIDE.md) for details.

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
# or: uv run a4d run-pipeline

# Common run-pipeline flags
just run --workers 8
just run --skip-upload          # Local testing: process but don't upload
just run --skip-download        # Reuse files already in data_root
just run --skip-drive-download  # Skip clinic_data.xlsx refresh from Google Drive
just run --skip-product         # Patient-only run
just run --skip-patient         # Product-only run (mutually exclusive with --skip-product)
just run --incremental          # Skip unchanged trackers (MD5 + completion match)
just run --force                # Wipe prior local outputs before each arm runs

# Single-arm runs (no GCS download/upload)
just run-local                  # Patient extract + clean + tables
just run-local-product          # Product extract + clean + tables
just run-file path/to/tracker.xlsx          # Single patient tracker
just run-file-product path/to/tracker.xlsx  # Single product tracker
```

## Architecture

```
run-pipeline flow:
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
│   ├── cli.py         # Typer CLI (process-patient, process-product, run-pipeline, …)
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

# Run all CI checks (format, lint, type, test)
just ci

# Run tests with coverage
just test

# Run tests without coverage (faster)
just test-fast

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

```bash
# All tests with coverage
just test
# or: uv run pytest --cov

# Fast tests (no coverage)
just test-fast
# or: uv run pytest -x

# Specific test file
uv run pytest tests/test_extract/test_patient.py
```

### Code Quality

```bash
# Run all checks (what CI runs)
just ci

# Individual checks
just lint          # Linting
just format        # Format code
just format-check  # Check formatting without changes
just check         # Type checking with ty
just fix           # Auto-fix linting issues
```

### Pre-commit Hooks

```bash
# Install hooks
just hooks
# or: uv run pre-commit install

# Run manually on all files
just hooks-run
# or: uv run pre-commit run --all-files
```

### Docker

```bash
# Build Docker image (tagged :latest and :<git-sha>)
just docker-build

# Smoke-test the image (CLI reachable inside the container)
just docker-smoke

# Push both tags to Artifact Registry
just docker-push

# Or manually:
docker build -t a4d-python:latest .
docker run --rm --env-file .env -v $(pwd)/output:/app/output a4d-python:latest
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

## Migration from R

This project is a complete rewrite of the R pipeline with:

- 2-5x performance improvement
- Patient + product trackers in a single orchestrated run
- Incremental processing (only changed files)
- Better error tracking and logging
- Simpler deployment (single Docker container)
- Modern Python best practices

See [docs/migration/](docs/migration/) for the migration guide and per-feature notes.

## License

MIT
