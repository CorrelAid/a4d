# A4D Data Processing Pipeline (Python)

Python implementation of the A4D medical tracker data processing pipeline.

## Migration Status

🚧 **Active Development** - Migrating from R to Python

See [Migration Documentation](../MIGRATION_OVERVIEW.md) for details.

## Features

- ✅ **Incremental Processing** - Only process changed tracker files
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
# Full pipeline
just run
# or: uv run python scripts/run_pipeline.py

# With options
just run --max-workers 8
just run --skip-upload  # Local testing
```

## Architecture

```
Pipeline Flow:
1. Query BigQuery metadata → determine changed files
2. Process changed trackers in parallel (extract → clean → validate)
3. Aggregate individual parquets → final tables
4. Upload to BigQuery
5. Update metadata table
```

## Project Structure

```
a4d-python/
├── src/a4d/           # Main package
│   ├── config.py      # Pydantic settings
│   ├── logging.py     # loguru configuration
│   ├── extract/       # Data extraction (Script 1)
│   ├── clean/         # Data cleaning (Script 2)
│   ├── tables/        # Table creation (Script 3)
│   ├── gcp/           # BigQuery & GCS integration
│   ├── state/         # State management
│   └── utils/         # Utilities
├── tests/             # Test suite
├── scripts/           # CLI scripts
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
# Build Docker image
just docker-build

# Run container locally
just docker-run

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
- Incremental processing (only changed files)
- Better error tracking and logging
- Simpler deployment (single Docker container)
- Modern Python best practices

See migration documentation in parent directory for details.

## License

MIT
