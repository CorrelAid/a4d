# R to Python Migration - Complete Overview

## Status: Ready to Begin ✅

This document provides a complete overview of the migration plan and serves as a checklist.

---

## Documents Created

| Document | Purpose | Status |
|----------|---------|--------|
| **MIGRATION_STRATEGY.md** | High-level strategy, tech stack, phases, timeline, risks | ✅ Complete |
| **PYTHON_MIGRATION_PLAN.md** | Detailed technical guide with code examples for all components | ✅ Complete |
| **PYTHON_MIGRATION_PLAN_ERROR_LOGGING.md** | Error tracking strategy (critical for data quality) | ✅ Complete |
| **ARCHITECTURE_PER_TRACKER.md** | Per-tracker processing architecture (rejected SQLite approach) | ✅ Complete |
| **ARCHITECTURE_STATELESS_GCP.md** | Final architecture: stateless GCP with BigQuery state | ✅ Complete |
| **CLAUDE.md** | Documentation for future Claude Code sessions | ✅ Already exists |

---

## Key Decisions Made ✅

### Architecture Decisions
- ✅ **Per-tracker processing** instead of batch-per-step (better for incremental, parallel processing)
- ✅ **No orchestrator** (Prefect/doit/Airflow) - simple Python + multiprocessing is sufficient
- ✅ **BigQuery metadata table** for state tracking (not SQLite - containers are stateless)
- ✅ **Incremental processing** via file hash comparison
- ✅ **Parallel processing** with ProcessPoolExecutor
- ✅ **Hybrid error logging** - vectorized conversions + detailed row-level error tracking for failures

### Technology Stack
- ✅ **Polars** - primary dataframe library (10-100x faster than pandas)
- ✅ **DuckDB** - complex SQL operations and aggregations
- ✅ **Pydantic** - type-safe configuration and data models
- ✅ **Pandera** - DataFrame schema validation
- ✅ **structlog** - structured JSON logging (matches R's log_to_json)
- ✅ **openpyxl / Polars** - Excel reading
- ✅ **google-cloud-bigquery** - replaces `bq` CLI
- ✅ **google-cloud-storage** - replaces `gsutil` CLI
- ✅ **pytest** - testing framework
- ✅ **uv** - dependency management
- ✅ **Docker** - containerization

---

## R Pipeline Components - Coverage Check

### Current R Pipeline Structure

```
R/
├── script1_*.R           (Extraction)
├── script2_*.R           (Cleaning)
├── script3_*.R           (Table creation)
├── helper_*.R            (Utilities)
├── logger.R              (Logging)
└── a4d-package.R         (Package definition)

scripts/R/
├── run_script_1_extract_raw_data.R
├── run_script_2_clean_data.R
├── run_script_3_create_tables.R
├── run_script_4_create_logs_table.R
├── run_script_5_create_metadata_table.R
└── run_pipeline.R

reference_data/
├── data_cleaning.yaml
├── master_tracker_variables.xlsx
├── clinic_data.xlsx (downloaded from Google Sheets)
├── synonyms/
│   ├── synonyms_patient.yaml
│   └── synonyms_product.yaml
└── provinces/
    └── allowed_provinces.yaml
```

### Python Migration Coverage

| R Component | Python Equivalent | Coverage Status |
|------------|-------------------|-----------------|
| **Configuration** | | |
| config.yml | Pydantic Settings (src/a4d/config.py) | ✅ Designed |
| .Renviron | .env file | ✅ Designed |
| **Logging** | | |
| logger.R | structlog (src/a4d/logging.py) | ✅ Designed |
| log_to_json() | structlog with JSON renderer | ✅ Designed |
| with_file_logger() | file_logger context manager | ✅ Designed |
| **Synonym Mapping** | | |
| read_column_synonyms() | SynonymMapper class | ✅ Designed |
| synonyms_patient.yaml | Same YAML files (reuse) | ✅ Compatible |
| synonyms_product.yaml | Same YAML files (reuse) | ✅ Compatible |
| **Data Validation** | | |
| data_cleaning.yaml | ColumnValidator + Pandera schemas | ✅ Designed |
| Schema as tibble | Pandera DataFrameModel | ✅ Designed |
| **Script 1: Extraction** | | |
| script1_process_tracker_file.R | tracker_pipeline.py | ✅ Designed |
| script1_process_patient_data.R | extract/patient.py | ✅ Designed |
| script1_process_product_data.R | extract/product.py | ⚠️ Mentioned, not detailed |
| script1_read_patient_data.R | Integrated in extract/patient.py | ✅ Designed |
| read_product_data.R | Integrated in extract/product.py | ⚠️ Mentioned, not detailed |
| **Script 2: Cleaning** | | |
| script2_process_patient_data.R | clean/patient.py | ✅ Designed |
| script2_process_product_data.R | clean/product.py | ⚠️ Mentioned, not detailed |
| script2_helper_patient_data_fix.R | clean/patient.py (fixes) | ✅ Designed |
| script2_helper_dates.R | clean/converters.py (date parsing) | ✅ Designed |
| script2_sanitize_str.R | Polars string methods | ✅ Designed |
| Error value constants | settings.error_val_* | ✅ Designed |
| Row-wise error logging | ErrorCollector + safe_convert_column | ✅ Designed |
| **Script 3: Tables** | | |
| script3_create_table_patient_data_static.R | tables/patient.py | ✅ Example shown |
| script3_create_table_patient_data.R | tables/patient.py | ✅ Example shown |
| script3_create_table_patient_data_annual.R | tables/patient.py | ⚠️ Mentioned, pattern shown |
| script3_create_table_patient_data_changes_only.R | tables/patient.py (DuckDB) | ✅ Example shown |
| script3_create_table_product_data.R | tables/product.py | ⚠️ Mentioned, not detailed |
| script3_create_table_clinic_static_data.R | tables/clinic.py | ⚠️ Mentioned, not detailed |
| script3_link_product_patient.R | tables/product.py | ⚠️ Mentioned, not detailed |
| **Script 4: Logs Table** | | |
| run_script_4_create_logs_table.R | Aggregate error parquets | ⚠️ **Not explicitly designed** |
| **Script 5: Metadata Table** | | |
| run_script_5_create_metadata_table.R | BigQueryStateManager.update_metadata() | ✅ Designed |
| **Pipeline Orchestration** | | |
| run_pipeline.R | scripts/run_pipeline.py | ✅ Designed |
| **GCP Integration** | | |
| system("gsutil ...") | google.cloud.storage | ✅ Designed |
| system("bq load ...") | google.cloud.bigquery | ✅ Designed |
| download_google_sheet() | Google Sheets API | ⚠️ **Not explicitly designed** |
| **Utilities** | | |
| helper_main.R (init_paths, get_files) | utils/paths.py | ✅ Designed |
| wide_format_2_long_format.R | Polars melt/pivot | ✅ Covered by Polars |
| **State Management** | | |
| N/A (didn't exist in R) | BigQueryStateManager | ✅ **New feature** |

---

## Identified Gaps (Minor)

These are components mentioned but not fully detailed. Not blockers - can be addressed during implementation:

### 1. Product Data Processing (⚠️ Medium Priority)
- **Gap**: Examples focus on patient data; product data follows same pattern but not explicitly shown
- **Impact**: Low - same patterns as patient data
- **Action**: Apply patient data patterns when implementing

### 2. All Table Creation Scripts (⚠️ Low Priority)
- **Gap**: Only patient_static and patient_monthly shown in detail
- **Missing**: patient_annual, product tables, clinic_static, product-patient linking
- **Impact**: Low - patterns are clear, DuckDB examples provided
- **Action**: Implement following shown patterns

### 3. Script 4 - Logs Table Creation (⚠️ Low Priority)
- **Gap**: Not explicitly designed in migration docs
- **Current**: Error logs saved as individual parquet files per tracker
- **Needed**: Aggregate all error parquets into single logs table
- **Impact**: Low - simple aggregation
- **Solution**:
  ```python
  # Read all error parquets
  error_files = list(Path("logs").glob("*_errors.parquet"))
  logs_df = pl.concat([pl.read_parquet(f) for f in error_files])
  logs_df.write_parquet("tables/table_logs.parquet")
  ```

### 4. Google Sheets Download (⚠️ Low Priority)
- **Gap**: Not explicitly designed
- **Current R**: `download_google_sheet()` downloads clinic_data.xlsx
- **Needed**: Python equivalent
- **Impact**: Low - standard Google API
- **Solution**:
  ```python
  from google.oauth2 import service_account
  from googleapiclient.discovery import build

  # Download Google Sheet as Excel
  # Similar to R implementation
  ```

### 5. Reference Data Migration (✅ No Action Needed)
- **Status**: All YAML files can be reused as-is
- **Files**:
  - synonyms_patient.yaml ✅
  - synonyms_product.yaml ✅
  - data_cleaning.yaml ✅
  - allowed_provinces.yaml ✅
  - master_tracker_variables.xlsx ✅ (reference only)

---

## Migration Phases - Detailed Checklist

### Phase 0: Foundation (Week 1-2)
- [ ] Create Python project structure
- [ ] Set up uv/Poetry dependency management
- [ ] Configure pyproject.toml with all dependencies
- [ ] Create Dockerfile
- [ ] Set up pre-commit hooks (ruff, mypy)
- [ ] Configure pytest
- [ ] Set up GitHub Actions CI/CD
- [ ] Create comparison utilities (compare R vs Python outputs)

### Phase 1: Core Infrastructure (Week 2-3)
- [ ] Implement config.py (Pydantic Settings)
- [ ] Implement logging.py (structlog)
- [ ] Implement synonyms/mapper.py
- [ ] Implement schemas/validation.py (Pandera + YAML)
- [ ] Implement clean/converters.py (ErrorCollector)
- [ ] Implement gcp/storage.py
- [ ] Implement gcp/bigquery.py
- [ ] Implement state/bigquery_state.py
- [ ] Write unit tests for infrastructure

### Phase 2: Script 1 - Data Extraction (Week 3-5)
- [ ] Implement extract/patient.py
- [ ] Implement extract/product.py
- [ ] Implement scripts/run_script_1.py (or integrate into main pipeline)
- [ ] Test on sample tracker files
- [ ] **Validate**: Compare raw parquets with R output
- [ ] Document any differences (intentional vs bugs)

### Phase 3: Script 2 - Data Cleaning (Week 5-7)
- [ ] Implement clean/patient.py with error tracking
- [ ] Implement clean/product.py with error tracking
- [ ] Implement all data fixes (vectorized where possible)
- [ ] Implement YAML validation rules
- [ ] Test on sample data
- [ ] **Validate**: Compare cleaned parquets with R output
- [ ] **Validate**: Compare error logs (count, patient_ids)
- [ ] Performance benchmark vs R

### Phase 4: Script 3 - Table Creation (Week 7-9)
- [ ] Implement tables/patient.py (all table types)
- [ ] Implement tables/product.py
- [ ] Implement tables/clinic.py
- [ ] Implement product-patient linking
- [ ] Implement logs table aggregation (Script 4)
- [ ] Test table creation
- [ ] **Validate**: Compare final tables with R output
- [ ] Document schema differences (if any)

### Phase 5: Pipeline Integration (Week 9-10)
- [ ] Implement pipeline/tracker_pipeline.py
- [ ] Implement scripts/run_pipeline.py
- [ ] Implement parallel processing
- [ ] Implement incremental processing (hash comparison)
- [ ] Implement metadata table creation/update
- [ ] Test end-to-end locally
- [ ] Test with subset of production data
- [ ] **Validate**: Full pipeline outputs vs R

### Phase 6: GCP Deployment (Week 10-11)
- [ ] Finalize Dockerfile
- [ ] Set up GCP service accounts and permissions
- [ ] Test GCS upload/download
- [ ] Test BigQuery ingestion
- [ ] Deploy to Cloud Run (test environment)
- [ ] Test with Cloud Scheduler trigger
- [ ] Set up monitoring and alerting
- [ ] Configure secrets (service account keys)

### Phase 7: Parallel Validation (Week 11-12)
- [ ] Run both R and Python pipelines on production data
- [ ] Automated comparison of all outputs
- [ ] Investigate any differences
- [ ] Performance benchmarking
- [ ] Memory profiling
- [ ] Fix bugs discovered
- [ ] Optimize bottlenecks

### Phase 8: Production Cutover (Week 12-13)
- [ ] Final validation sign-off
- [ ] Update documentation
- [ ] Team training session
- [ ] Deploy to production Cloud Run
- [ ] Monitor first production run
- [ ] Deprecate R pipeline
- [ ] Celebrate! 🎉

---

## Testing Strategy

### Unit Tests
```
tests/
├── test_config.py          # Configuration loading
├── test_logging.py         # Logging functionality
├── test_synonyms.py        # Synonym mapping
├── test_converters.py      # Type conversion + error tracking
├── test_validators.py      # YAML validation rules
└── test_gcp.py            # GCP integration (mocked)
```

### Integration Tests
```
tests/integration/
├── test_extract.py         # Full extraction on sample tracker
├── test_clean.py           # Full cleaning on sample data
├── test_tables.py          # Table creation
└── test_pipeline.py        # End-to-end pipeline
```

### Comparison Tests
```
tests/comparison/
├── test_raw_output.py      # Compare Script 1 outputs
├── test_cleaned_output.py  # Compare Script 2 outputs
├── test_tables_output.py   # Compare Script 3 outputs
└── test_error_logs.py      # Compare error counts
```

---

## Reference Data - Migration Plan

| File | Location | Action | Status |
|------|----------|--------|--------|
| synonyms_patient.yaml | reference_data/synonyms/ | Copy as-is | ✅ No changes needed |
| synonyms_product.yaml | reference_data/synonyms/ | Copy as-is | ✅ No changes needed |
| data_cleaning.yaml | reference_data/ | Copy as-is | ✅ No changes needed |
| allowed_provinces.yaml | reference_data/provinces/ | Copy as-is | ✅ No changes needed |
| master_tracker_variables.xlsx | reference_data/ | Reference only | ✅ No migration needed |
| clinic_data.xlsx | reference_data/ | Download in pipeline | ⚠️ Add Google Sheets download |

---

## Key Patterns to Apply

### 1. R dplyr → Polars
```python
# R: df %>% filter(age > 18) %>% select(name, age)
# Python:
df.filter(pl.col("age") > 18).select(["name", "age"])
```

### 2. R rowwise() → Vectorized + Error Tracking
```python
# R: df %>% rowwise() %>% mutate(age_fixed = fix_age(age, dob, ...))
# Python: Vectorized with ErrorCollector for failures
df = safe_convert_column(df, "age", pl.Int32, error_collector)
```

### 3. R log_to_json → structlog
```python
# R: logInfo(log_to_json("Message {val}", values = list(val = x)))
# Python:
logger.info("Message", val=x)  # Automatically JSON-formatted
```

### 4. R tryCatch → try/except with logging
```python
# R: tryCatch(process(), error = function(e) logError(...))
# Python:
try:
    process()
except Exception as e:
    logger.error("Failed", error=str(e), exc_info=True)
```

---

## Success Criteria

### Correctness
- [ ] All final tables match R output (or documented differences)
- [ ] Error counts match R pipeline
- [ ] Same patient_ids flagged for errors
- [ ] Data quality checks pass

### Performance
- [ ] 2-5x faster than R pipeline
- [ ] Incremental runs process only changed files
- [ ] Memory usage acceptable (<8GB)

### Code Quality
- [ ] Test coverage >80%
- [ ] All public functions have type hints
- [ ] Ruff linting passes
- [ ] mypy type checking passes
- [ ] Documentation complete

### Deployment
- [ ] Cloud Run deployment works
- [ ] Incremental processing works in GCP
- [ ] BigQuery metadata tracking works
- [ ] Monitoring and alerting set up

---

## Questions to Answer During Migration

These don't need answers now, but will come up:

1. **Exact data type conversions**: Some R/Polars type differences may need attention
2. **Date parsing edge cases**: Different parsers might handle ambiguous dates differently
3. **Floating point precision**: Check if numeric comparisons need tolerance
4. **Memory optimization**: May need streaming for very large files
5. **Parallel processing tuning**: Optimal number of workers for Cloud Run
6. **BigQuery query costs**: Monitor costs for metadata queries
7. **Error message parity**: Ensure Python errors are as useful as R errors

---

## Risk Mitigation

| Risk | Mitigation | Status |
|------|-----------|--------|
| Output differences | Automated comparison at each phase | ✅ Planned |
| Performance regression | Benchmark each phase | ✅ Planned |
| Deployment issues | Test in staging environment first | ✅ Planned |
| Data loss | Parallel running until validated | ✅ Planned |
| Team adoption | Documentation + training | ✅ Planned |

---

## What We Have

✅ **Strategic direction**: Clear architecture and approach
✅ **Technology choices**: Modern, well-suited stack
✅ **Core patterns**: How to migrate each component
✅ **Critical details**: Error logging, state management, GCP integration
✅ **Validation plan**: Ensure correctness at each step
✅ **Deployment strategy**: Stateless GCP-native approach

## What We Don't Have (Intentionally)

❌ Line-by-line migration of every R function (you'll read these during implementation)
❌ Every table creation script in detail (patterns are clear, apply as needed)
❌ Complete unit test suite (write during development)
❌ Exact data type mappings for every column (discover during implementation)

## What's Missing (Can Add if Needed)

⚠️ Script 4 (logs table) - simple aggregation, add during Phase 4
⚠️ Google Sheets download - standard API, add during Phase 1
⚠️ Product data details - same patterns as patient data

---

## Next Steps

1. **Review this document** - Is this the right level of detail?
2. **Approve approach** - Any concerns with architecture or tech choices?
3. **Start Phase 0** - Set up Python project structure
4. **Create first PR** - Foundation code (config, logging, synonyms)
5. **Iterate** - Build incrementally, validate continuously

---

## Timeline Summary

| Phase | Duration | Deliverable | Validation |
|-------|----------|-------------|------------|
| 0: Foundation | 1-2 weeks | Project setup | Tests pass, CI works |
| 1: Infrastructure | 1 week | Core libraries | Unit tests pass |
| 2: Extraction | 2 weeks | Script 1 | Outputs match R |
| 3: Cleaning | 2 weeks | Script 2 | Outputs match R |
| 4: Tables | 2 weeks | Script 3-5 | Outputs match R |
| 5: Pipeline | 1 week | Full pipeline | End-to-end match |
| 6: GCP | 1 week | Cloud deployment | Runs in Cloud Run |
| 7: Validation | 1 week | Parallel runs | Production parity |
| 8: Cutover | 1 week | Go live | Success! |

**Total**: ~12-13 weeks

---

## Conclusion

**We have everything we need to start.**

The plan is at the right level:
- ✅ Strategic direction is clear
- ✅ Architecture decisions are made
- ✅ Technology stack is chosen
- ✅ Core patterns are documented
- ✅ Critical challenges are addressed (error logging, state management)
- ✅ Validation strategy is defined
- ✅ Minor gaps identified (easily addressed during implementation)

The migration docs provide:
1. **What to build** (architecture, components)
2. **How to build it** (code patterns, examples)
3. **How to validate it** (comparison strategy)
4. **How to deploy it** (GCP stateless approach)

You're ready to begin Phase 0! 🚀
