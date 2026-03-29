# Feature Proposal: Product Data Processing Pipeline

## Summary

Implement a complete product data processing pipeline in the Python codebase to match the functionality of the R pipeline. This is a critical gap as the R pipeline processes both patient AND product data, while the Python pipeline currently only handles patient data.

## Problem Statement

The Python pipeline is missing product data processing capabilities that exist in the R pipeline:

1. **R Pipeline has extensive product data processing:**
   - `script1_process_product_data.R` - Extract product data from Excel
   - `script2_process_product_data.R` - Clean product data
   - `script3_create_table_product_data.R` - Create product data table
   - `script3_link_product_patient.R` - Link product and patient data
   - `helper_product_data.R` - Product data utilities
   - `read_product_data.R` - Product data reading functions

2. **Python Pipeline only has patient data processing:**
   - `extract/patient.py` - Extract patient data
   - `clean/patient.py` - Clean patient data
   - `tables/patient.py` - Create patient tables
   - **No product data modules exist**

3. **Infrastructure already exists for product data:**
   - `reference/synonyms.py` has `load_product_mapper()` function
   - `gcp/bigquery.py` includes `product_data` in table schemas
   - `reference_data/synonyms/synonyms_product.yaml` exists

## Proposed Solution

Implement a complete product data processing pipeline with the following components:

### 1. Product Data Extraction (`src/a4d/extract/product.py`)

Extract product data from Excel tracker files:

- Read product sheets from Excel files
- Use product column mapper to rename columns
- Extract product information (product name, units, dates, etc.)
- Handle multiple product entries per tracker
- Export to parquet format

### 2. Product Data Cleaning (`src/a4d/clean/product.py`)

Clean and validate product data:

- Validate product names against reference data
- Clean product units and quantities
- Parse product dates
- Validate product balances
- Track data quality errors
- Handle missing values

### 3. Product Data Table Creation (`src/a4d/tables/product.py`)

Create final product data tables:

- Merge all cleaned product parquet files
- Create product_data table with proper schema
- Link product data with patient data
- Calculate product balance status
- Export to parquet for BigQuery upload

### 4. Product Data Pipeline (`src/a4d/pipeline/product.py`)

Orchestrate product data processing:

- Discover tracker files with product data
- Process product data in parallel (like patient pipeline)
- Create product tables
- Integrate with existing pipeline

### 5. CLI Commands (`src/a4d/cli.py`)

Add product data CLI commands:

- `process-product` - Run product data pipeline
- `create-product-tables` - Create tables from existing cleaned data
- Update `process-patient` to optionally process product data

## Architecture

```
Product Data Pipeline Flow:
1. Discover tracker files with product sheets
2. For each tracker (parallel):
   - Extract product data from Excel → raw parquet
   - Clean raw data → cleaned parquet
3. Create final product table from all cleaned parquets
4. Link product data with patient data
5. Upload to BigQuery
```

## Implementation Plan

### Phase 1: Core Product Data Processing

1. Create `src/a4d/extract/product.py` - Product data extraction
2. Create `src/a4d/clean/product.py` - Product data cleaning
3. Create `src/a4d/tables/product.py` - Product table creation
4. Create `src/a4d/pipeline/product.py` - Product pipeline orchestration

### Phase 2: CLI Integration

5. Add `process-product` command to CLI
2. Add `create-product-tables` command to CLI
3. Update `process-patient` to support product data

### Phase 3: Testing & Documentation

8. Add unit tests for product data modules
2. Add integration tests for product pipeline
3. Update documentation

## Benefits

1. **Feature Parity**: Python pipeline matches R pipeline functionality
2. **Complete Data Processing**: Process both patient AND product data
3. **BigQuery Integration**: Product data table can be uploaded to BigQuery
4. **Data Linking**: Link product usage with patient outcomes
5. **Inventory Tracking**: Track medical supply distribution

## Dependencies

- Existing product mapper: `load_product_mapper()` in `reference/synonyms.py`
- Product synonyms YAML: `reference_data/synonyms/synonyms_product.yaml`
- BigQuery schema: `product_data` table already defined in `gcp/bigquery.py`

## Success Criteria

- [ ] Product data can be extracted from Excel tracker files
- [ ] Product data is cleaned and validated
- [ ] Product data table is created with correct schema
- [ ] Product data can be linked with patient data
- [ ] Product data can be uploaded to BigQuery
- [ ] All tests pass
- [ ] Documentation is updated

## Questions for User

1. Should product data processing be integrated into the existing `process-patient` command, or should it be a separate `process-product` command?
2. Are there any specific product data validation rules that should be added?
3. Should product data processing be enabled by default, or require an explicit flag?
