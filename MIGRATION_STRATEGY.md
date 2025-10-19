# R to Python Migration Strategy

## Executive Summary

This document outlines the strategy for migrating the A4D data processing pipeline from R to Python. The migration aims to improve performance, maintainability, deployment simplicity, and leverage modern Python data engineering tools while preserving exact output compatibility.

## Goals and Objectives

### Primary Goals
1. **Output Compatibility**: Generate identical Parquet files with the same data (unless fixing bugs)
2. **Performance**: Achieve significant speed improvements through modern Python tools
3. **Maintainability**: Cleaner, more readable code following Python best practices
4. **Deployment**: Simplified GCP deployment with containerization
5. **Modernization**: Leverage best-in-class Python data engineering tools

### Success Criteria
- All output tables match R pipeline results (validated via automated comparison)
- Pipeline runs 2-5x faster than R version
- Reduced code complexity and improved readability
- Simplified deployment process
- Comprehensive test coverage (>80%)

## Technology Stack

### Core Data Processing
- **Polars** (primary dataframe library)
  - 10-100x faster than pandas for large datasets
  - Lazy evaluation and query optimization
  - Native Parquet support with excellent compression
  - Expressive API similar to dplyr
  - Better memory management than pandas

- **DuckDB** (SQL analytics)
  - For complex aggregations and joins
  - Direct Parquet file querying
  - Excellent for cross-file operations
  - Can work directly with Polars DataFrames

### Data Validation & Schema Management
- **Pydantic** (data validation)
  - Type-safe configuration management
  - Runtime validation
  - Automatic JSON schema generation
  - Integration with modern Python tooling

- **Pandera** (DataFrame schema validation)
  - Schema-based DataFrame validation
  - Integration with Polars
  - Descriptive error messages
  - Can validate against allowed values (YAML configs)

### Pipeline Orchestration
- **Prefect** (recommended) or **doit**
  - **Prefect**: Modern workflow orchestration, cloud-native, better observability
  - **doit**: Simpler, file-based dependency management, no server required
  - Both support task dependencies, retries, and parallel execution

### File I/O
- **openpyxl** (Excel reading)
  - Pure Python, well-maintained
  - Alternative: **polars.read_excel()** (wrapper around calamine, very fast)

- **PyArrow** / **Polars native** (Parquet I/O)
  - Native Parquet support in Polars
  - Excellent compression and performance

### GCP Integration
- **google-cloud-bigquery** (Python SDK)
  - Programmatic API instead of CLI tools
  - Better error handling and logging
  - Native Python integration
  - Supports direct Parquet upload

- **google-cloud-storage** (GCS operations)
  - Replace gsutil with Python SDK
  - Parallel upload/download
  - Better progress tracking

### Logging & Monitoring
- **structlog** (structured logging)
  - JSON-formatted logs (like current system)
  - Context binding for request tracking
  - Integration with cloud logging
  - Human-readable development logs

### Configuration & Environment
- **pydantic-settings** (configuration)
  - Type-safe settings from environment variables
  - Replaces config.yml with Python classes
  - Validation of configuration values

- **Poetry** or **uv** (dependency management)
  - Modern Python dependency management
  - Lock files for reproducible builds
  - Better than pip + requirements.txt

### Development Tools
- **pytest** (testing)
- **ruff** (linting & formatting, replaces black + flake8 + isort)
- **mypy** (type checking)
- **pre-commit** (git hooks)

## Migration Approach

### Strategy: Phased Incremental Migration

We'll use an incremental approach with parallel validation rather than big-bang replacement.

### Phases

#### Phase 0: Foundation (Weeks 1-2)
- Set up Python project structure
- Configure dependency management (Poetry/uv)
- Create Docker containerization
- Set up CI/CD pipeline
- Establish testing framework
- Create comparison/validation utilities

#### Phase 1: Core Infrastructure (Weeks 2-3)
- Configuration management (Pydantic settings)
- Logging infrastructure (structlog)
- Synonym mapping system (YAML → Python)
- Data validation schema (Pandera)
- GCP integration utilities
- Path management utilities

#### Phase 2: Script 1 - Data Extraction (Weeks 3-5)
- Excel reading with Polars
- Synonym-based column mapping
- Patient data extraction
- Product data extraction
- Raw Parquet export
- **Validation**: Compare raw outputs with R pipeline

#### Phase 3: Script 2 - Data Cleaning (Weeks 5-7)
- Type conversion logic
- Data validation (Pandera + YAML config)
- Cleaning transformations
- Error value handling
- **Validation**: Compare cleaned outputs with R pipeline

#### Phase 4: Script 3 - Table Creation (Weeks 7-9)
- Patient data tables (static, monthly, annual)
- Product data tables
- Longitudinal data tables
- Clinic static data
- Product-patient linking
- **Validation**: Compare final tables with R pipeline

#### Phase 5: Orchestration & Deployment (Weeks 9-10)
- Pipeline orchestration (Prefect/doit)
- GCP BigQuery ingestion
- Docker containerization
- Cloud Run / Compute Engine deployment
- Monitoring and alerting

#### Phase 6: Parallel Validation & Optimization (Weeks 10-12)
- Run both pipelines in parallel on production data
- Automated difference detection
- Performance benchmarking
- Memory profiling and optimization
- Final bug fixes

#### Phase 7: Transition (Week 12-13)
- Documentation updates
- Team training
- Production cutover
- R pipeline deprecation

### Validation Strategy

**Automated Comparison Framework**:
```python
# Compare Parquet files from R and Python pipelines
def compare_outputs(r_path, py_path):
    r_df = pl.read_parquet(r_path)
    py_df = pl.read_parquet(py_path)

    # Schema comparison
    # Row count comparison
    # Value-by-value comparison
    # Statistical summaries
    # Generate diff report
```

**Continuous Validation**:
- Run comparison after each phase
- Track differences in version control
- Document intentional differences (bug fixes)
- Fail CI/CD if unexpected differences found

## Migration Patterns

### R to Python Equivalents

| R Pattern | Python Equivalent |
|-----------|-------------------|
| `dplyr::mutate()` | `pl.DataFrame.with_columns()` |
| `dplyr::filter()` | `pl.DataFrame.filter()` |
| `dplyr::rowwise()` | Avoid! Use vectorized operations or `map_elements()` |
| `readxl::read_excel()` | `pl.read_excel()` or `openpyxl` |
| `arrow::write_parquet()` | `pl.DataFrame.write_parquet()` |
| `ParallelLogger` | `structlog` |
| `yaml::read_yaml()` | `pyyaml` or embed in Pydantic models |
| `config::get()` | Pydantic Settings |
| `system("gsutil")` | `google.cloud.storage` |
| `system("bq")` | `google.cloud.bigquery` |

### Key Pattern Changes

1. **Avoid Row-wise Operations**
   - R: `dplyr::rowwise()` is common but slow
   - Python: Use Polars' vectorized operations or DuckDB SQL
   - Example: Type conversions should be vectorized, not row-wise

2. **Schema-First Approach**
   - R: Schema defined as tibble, then merge
   - Python: Pydantic/Pandera schemas, validated upfront
   - Better error messages and type safety

3. **Error Handling**
   - R: `tryCatch()` with logging
   - Python: Try/except with structured logging context
   - More granular error types

4. **Synonym Matching**
   - R: YAML → tibble → matching
   - Python: YAML → dict/Pydantic → efficient lookup
   - Consider fuzzy matching for better column detection

## Project Structure

```
a4d-python/
├── pyproject.toml              # Poetry/uv dependencies
├── README.md
├── MIGRATION_STRATEGY.md       # This file
├── PYTHON_MIGRATION_PLAN.md    # Detailed technical plan
├── Dockerfile
├── .env.example
├── src/
│   └── a4d/
│       ├── __init__.py
│       ├── config.py           # Pydantic settings
│       ├── logging.py          # structlog setup
│       ├── schemas/            # Pydantic/Pandera schemas
│       │   ├── patient.py
│       │   ├── product.py
│       │   └── validation.py
│       ├── synonyms/           # Synonym mapping
│       │   └── mapper.py
│       ├── extract/            # Script 1
│       │   ├── excel.py
│       │   ├── patient.py
│       │   └── product.py
│       ├── clean/              # Script 2
│       │   ├── patient.py
│       │   ├── product.py
│       │   └── validators.py
│       ├── tables/             # Script 3
│       │   ├── patient.py
│       │   ├── product.py
│       │   └── clinic.py
│       ├── gcp/                # GCP integration
│       │   ├── storage.py
│       │   └── bigquery.py
│       └── utils/
│           ├── paths.py
│           └── errors.py
├── scripts/                    # CLI entry points
│   ├── run_script_1.py
│   ├── run_script_2.py
│   ├── run_script_3.py
│   └── run_pipeline.py
├── tests/
│   ├── conftest.py
│   ├── test_extract/
│   ├── test_clean/
│   ├── test_tables/
│   └── comparison/             # R vs Python validation
│       └── test_output_equivalence.py
├── reference_data/             # Existing YAML files
│   ├── data_cleaning.yaml
│   ├── master_tracker_variables.xlsx
│   └── synonyms/
└── docs/
    └── migration_progress.md
```

## Risk Management

### Technical Risks

| Risk | Mitigation |
|------|-----------|
| Output differences from R | Automated comparison framework, phase-by-phase validation |
| Performance issues | Early benchmarking, profiling, use of lazy evaluation |
| Dependency conflicts | Poetry lock files, Docker containerization |
| GCP API changes | Use official SDK, version pinning, integration tests |
| Data loss during migration | Parallel running, extensive validation before cutover |

### Project Risks

| Risk | Mitigation |
|------|-----------|
| Timeline overrun | Phased approach allows partial completion, prioritize core features |
| Knowledge gaps | Documentation, pair programming, code reviews |
| Regression bugs | Comprehensive test suite, automated comparison |
| Team adoption | Training sessions, clear documentation, gradual transition |

## Testing Strategy

1. **Unit Tests**: Individual functions with pytest
2. **Integration Tests**: End-to-end pipeline runs on sample data
3. **Comparison Tests**: R vs Python output validation
4. **Performance Tests**: Benchmark against R version
5. **Data Quality Tests**: Schema validation, data integrity checks

## Deployment Strategy

### Local Development
- Docker Compose for local testing
- Use `.env` for configuration
- Mock GCP services for development

### GCP Production
- **Option 1**: Cloud Run (serverless, auto-scaling)
  - Triggered by Cloud Scheduler
  - Best for intermittent workloads

- **Option 2**: Compute Engine VM
  - For long-running processes
  - More control over resources

- **Container Registry**: Artifact Registry
- **Secrets Management**: Secret Manager
- **Monitoring**: Cloud Monitoring + structlog

## Timeline Estimate

- **Total Duration**: 12-13 weeks
- **Critical Path**: Data extraction → Cleaning → Tables → Validation
- **Parallel Tracks**: Infrastructure can be developed alongside extraction

## Success Metrics

1. **Correctness**: 100% output match (or documented differences)
2. **Performance**: 2-5x speed improvement
3. **Code Quality**:
   - Test coverage > 80%
   - Type hints on all public APIs
   - Linting score > 9/10
4. **Deployment**:
   - One-command deployment
   - < 5 min to deploy
5. **Maintainability**:
   - Reduced lines of code
   - Improved documentation
   - Easier onboarding

## Next Steps

1. Review and approve this strategy document
2. Set up Python project repository structure
3. Create detailed sprint plans from Phase 0
4. Begin Phase 0: Foundation work
5. Schedule weekly progress reviews

## Questions to Resolve

1. Prefect vs doit for orchestration? (Recommendation: Prefect if cloud budget allows, doit if simplicity preferred)
2. Deploy to Cloud Run or Compute Engine? (Recommendation: Start with Cloud Run for simplicity)
3. Keep R pipeline running in parallel indefinitely or time-bound? (Recommendation: 2-4 weeks parallel validation, then deprecate)
4. Migrate tests alongside or after? (Recommendation: Alongside, test-driven migration)
