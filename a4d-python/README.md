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

# Install dependencies
uv sync

# Install development dependencies
uv sync --group dev
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
uv run python scripts/run_pipeline.py

# With options
uv run python scripts/run_pipeline.py --max-workers 8
uv run python scripts/run_pipeline.py --force  # Reprocess all files
uv run python scripts/run_pipeline.py --skip-upload  # Local testing
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

### Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov

# Specific test file
uv run pytest tests/test_extract/test_patient.py
```

### Code Quality

```bash
# Linting
uv run ruff check .

# Formatting
uv run ruff format .

# Type checking
uv run mypy src/
```

### Pre-commit Hooks

```bash
# Install hooks
uv run pre-commit install

# Run manually
uv run pre-commit run --all-files
```

## Technology Stack

- **Polars** - Fast dataframe operations
- **DuckDB** - Complex SQL aggregations
- **Pydantic** - Type-safe configuration
- **Pandera** - DataFrame validation
- **loguru** - Structured JSON logging
- **Google Cloud SDK** - BigQuery & GCS
- **pytest** - Testing framework
- **uv** - Dependency management

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
