# Reference Data Migration Plan

This document describes how reference data and configuration files are used in the R pipeline and how to migrate them to Python.

## Overview

The R pipeline uses several YAML and Excel files for configuration and reference data:

| File | Purpose | R Usage | Python Migration Strategy |
|------|---------|---------|---------------------------|
| `config.yml` | GCP configuration, paths | Loaded via `config::get()` | Pydantic Settings with `.env` |
| `synonyms_patient.yaml` | Column name mappings (patient) | Script 1 - column renaming | `synonyms/mapper.py` loader |
| `synonyms_product.yaml` | Column name mappings (product) | Script 1 - column renaming | `synonyms/mapper.py` loader |
| `allowed_provinces.yaml` | Valid provinces by country | Script 2 - validation | Load into Pandera schema |
| `data_cleaning.yaml` | Validation rules | Script 2 - cleaning | `clean/rules.py` parser |
| `clinic_data.xlsx` | Static clinic info | Script 3 - table creation | Later phase (not needed initially) |

## Detailed Analysis

### 1. config.yml

**Current R Implementation:**
```r
# R/helper_main.R:15
config <- config::get()
paths$tracker_root <- config$data_root
paths$output_root <- file.path(config$data_root, config$output_dir)

# Access:
config$data_root
config$download_bucket
config$upload_bucket
config$project_id
config$dataset
```

**Structure:**
```yaml
default:
    download_bucket: "a4dphase2_upload"
    upload_bucket: "a4dphase2_output"
    data_root: "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload"
    output_dir: "output"
    project_id: "a4dphase2"
    dataset: "tracker"

production:
    data_root: "/home/rstudio/data"
```

**Python Migration:**
- ✅ **DONE** - Already implemented in `a4d/config.py` using Pydantic Settings
- Uses `.env` file instead of YAML (more standard for Python)
- Environment variables prefixed with `A4D_`
- Access: `settings.data_root`, `settings.upload_bucket`, etc.

**Action:** No additional work needed.

---

### 2. synonyms_patient.yaml & synonyms_product.yaml

**Current R Implementation:**
```r
# R/helper_main.R:69-78
get_synonyms <- function() {
    synonyms_patient <- read_column_synonyms(synonym_file = "synonyms_patient.yaml")
    synonyms_product <- read_column_synonyms(synonym_file = "synonyms_product.yaml")
    list(patient = synonyms_patient, product = synonyms_product)
}

# R/helper_main.R:99-126
read_column_synonyms <- function(synonym_file, path_prefixes = c("reference_data", "synonyms")) {
    path <- do.call(file.path, as.list(c(path_prefixes, synonym_file)))
    synonyms_yaml <- yaml::read_yaml(path)

    # Converts to tibble with columns: unique_name, synonym
    # e.g., "age" -> ["Age", "Age*", "age on reporting", ...]
}

# Used in Script 1 to rename columns during extraction
```

**Structure (example from synonyms_patient.yaml):**
```yaml
age:
  - Age
  - Age*
  - age on reporting
  - Age (Years)
  - Age* On Reporting
blood_pressure_dias_mmhg:
  - Blood Pressure Diastolic (mmHg)
patient_id:
  - ID
  - Patient ID
  - Patient ID*
```

**Python Migration Strategy:**

Create `src/a4d/synonyms/mapper.py`:
```python
from pathlib import Path
import yaml
from typing import Dict, List

class ColumnMapper:
    """Maps synonym column names to standardized names."""

    def __init__(self, yaml_file: Path):
        with open(yaml_file) as f:
            self.synonyms = yaml.safe_load(f)

        # Build reverse lookup: synonym -> standard_name
        self._lookup = {}
        for standard_name, synonyms in self.synonyms.items():
            for synonym in synonyms:
                self._lookup[synonym] = standard_name

    def rename_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        """Rename DataFrame columns using synonym mappings."""
        rename_map = {
            col: self._lookup.get(col, col)
            for col in df.columns
        }
        return df.rename(rename_map)

    def get_standard_name(self, column: str) -> str:
        """Get standard name for a column (or return original if not found)."""
        return self._lookup.get(column, column)

# Usage:
patient_mapper = ColumnMapper(Path("reference_data/synonyms/synonyms_patient.yaml"))
product_mapper = ColumnMapper(Path("reference_data/synonyms/synonyms_product.yaml"))

df = patient_mapper.rename_columns(df)
```

**Files to Create:**
- `src/a4d/synonyms/__init__.py`
- `src/a4d/synonyms/mapper.py`
- `tests/test_synonyms/test_mapper.py`

**Phase:** Phase 1 (Core Infrastructure)

---

### 3. allowed_provinces.yaml

**Current R Implementation:**
```r
# R/helper_main.R:149-153
get_allowed_provinces <- function() {
    provinces <- yaml::read_yaml("reference_data/provinces/allowed_provinces.yaml") %>%
        unlist()
    return(provinces)
}

# reference_data/build_package_data.R:1-8
# Provinces are injected into data_cleaning.yaml at build time
cleaning_config <- yaml::read_yaml("reference_data/data_cleaning.yaml")
allowed_provinces <- yaml::read_yaml("reference_data/provinces/allowed_provinces.yaml") %>% unlist()

for (i in length(cleaning_config$province$steps)) {
    if (cleaning_config$province$steps[[i]]$type == "allowed_values") {
        cleaning_config$province$steps[[i]]$allowed_values <- allowed_provinces
    }
}
```

**Structure:**
```yaml
THAILAND:
  - Amnat Charoen
  - Ang Thong
  - Bangkok
  ...
LAOS:
  - Attapeu
  - Bokeo
  ...
VIETNAM:
  - An Giang
  - Bà Rịa–Vũng Tàu
  ...
```

**Python Migration Strategy:**

Load into Pandera schema or validation rules:

```python
# src/a4d/schemas/provinces.py
import yaml
from pathlib import Path
from typing import List

def load_allowed_provinces() -> List[str]:
    """Load all allowed provinces from YAML file."""
    path = Path("reference_data/provinces/allowed_provinces.yaml")
    with open(path) as f:
        provinces_by_country = yaml.safe_load(f)

    # Flatten all provinces into single list
    all_provinces = []
    for country, provinces in provinces_by_country.items():
        all_provinces.extend(provinces)

    return all_provinces

ALLOWED_PROVINCES = load_allowed_provinces()

# Use in Pandera schema:
import pandera.polars as pa

class PatientSchema(pa.DataFrameModel):
    province: pl.Utf8 = pa.Field(isin=ALLOWED_PROVINCES, nullable=True)
```

**Files to Create:**
- `src/a4d/schemas/provinces.py`
- Update `src/a4d/schemas/patient.py` to use ALLOWED_PROVINCES

**Phase:** Phase 1 (Core Infrastructure)

---

### 4. data_cleaning.yaml

**Current R Implementation:**
```r
# reference_data/build_package_data.R:1-12
# Embedded into R package as sysdata.rda
cleaning_config <- yaml::read_yaml("reference_data/data_cleaning.yaml")
# ... inject provinces ...
config <- list(cleaning = cleaning_config)
save(config, file = "R/sysdata.rda")

# R/script2_helper_patient_data_fix.R:293-300
parse_character_cleaning_config <- function(config) {
    allowed_value_expr <- list()
    for (column in names(config)) {
        allowed_value_expr[[column]] <- parse_character_cleaning_pipeline(column, config[[column]])
    }
    allowed_value_expr
}

# R/script2_process_patient_data.R:303
# Used in mutate() to apply all validation rules
mutate(
    !!!parse_character_cleaning_config(a4d:::config$cleaning)
)
```

**Structure:**
```yaml
analog_insulin_long_acting:
  steps:
    - allowed_values: ["N", "Y"]
      replace_invalid: true
      type: allowed_values

insulin_regimen:
  steps:
    - function_name: extract_regimen
      type: basic_function
    - allowed_values:
        - "Basal-bolus (MDI)"
        - "Premixed 30/70 DB"
        - "Self-mixed BD"
        - "Modified conventional TID"
      replace_invalid: false
      type: allowed_values

province:
  steps:
    - allowed_values: [... provinces injected at build time ...]
      replace_invalid: true
      type: allowed_values
```

**Python Migration Strategy:**

Create a validation rules system:

```python
# src/a4d/clean/rules.py
import yaml
from pathlib import Path
from typing import Dict, List, Any, Callable
from dataclasses import dataclass
import polars as pl

@dataclass
class ValidationStep:
    """Single validation step from data_cleaning.yaml"""
    type: str  # "allowed_values", "basic_function", etc.
    allowed_values: List[str] = None
    replace_invalid: bool = False
    function_name: str = None
    error_value: str = None

@dataclass
class ColumnValidation:
    """All validation steps for a single column"""
    column_name: str
    steps: List[ValidationStep]

class ValidationRules:
    """Loads and applies validation rules from data_cleaning.yaml"""

    def __init__(self, yaml_path: Path):
        with open(yaml_path) as f:
            self.config = yaml.safe_load(f)

        self.rules = self._parse_rules()
        self.custom_functions = self._load_custom_functions()

    def _parse_rules(self) -> Dict[str, ColumnValidation]:
        """Parse YAML into structured validation rules."""
        rules = {}
        for column, config in self.config.items():
            steps = [
                ValidationStep(
                    type=step["type"],
                    allowed_values=step.get("allowed_values"),
                    replace_invalid=step.get("replace_invalid", False),
                    function_name=step.get("function_name"),
                    error_value=step.get("error_value")
                )
                for step in config.get("steps", [])
            ]
            rules[column] = ColumnValidation(column, steps)
        return rules

    def _load_custom_functions(self) -> Dict[str, Callable]:
        """Load custom validation functions (e.g., extract_regimen)."""
        from a4d.clean import converters
        return {
            "extract_regimen": converters.extract_regimen,
            # Add other custom functions here
        }

    def apply_to_column(self,
                       df: pl.DataFrame,
                       column: str,
                       error_collector: ErrorCollector) -> pl.DataFrame:
        """Apply all validation rules to a single column."""
        if column not in self.rules:
            return df

        validation = self.rules[column]
        for step in validation.steps:
            if step.type == "allowed_values":
                df = self._apply_allowed_values(
                    df, column, step, error_collector
                )
            elif step.type == "basic_function":
                func = self.custom_functions[step.function_name]
                df = func(df, column, error_collector)

        return df

    def _apply_allowed_values(self,
                             df: pl.DataFrame,
                             column: str,
                             step: ValidationStep,
                             error_collector: ErrorCollector) -> pl.DataFrame:
        """Validate column values against allowed list."""
        # Vectorized check
        is_valid = df[column].is_in(step.allowed_values) | df[column].is_null()

        # Log failures
        failed_rows = df.filter(~is_valid)
        for row in failed_rows.iter_rows(named=True):
            error_collector.add_error(
                file_name=row["file_name"],
                patient_id=row.get("patient_id"),
                column=column,
                original_value=row[column],
                error=f"Value not in allowed list: {step.allowed_values}"
            )

        # Replace if configured
        if step.replace_invalid:
            error_value = step.error_value or settings.error_val_character
            df = df.with_columns(
                pl.when(~is_valid)
                  .then(pl.lit(error_value))
                  .otherwise(pl.col(column))
                  .alias(column)
            )

        return df

# Usage in script 2:
rules = ValidationRules(Path("reference_data/data_cleaning.yaml"))
for column in df.columns:
    df = rules.apply_to_column(df, column, error_collector)
```

**Files to Create:**
- `src/a4d/clean/rules.py`
- `src/a4d/clean/converters.py` (custom validation functions like extract_regimen)
- `tests/test_clean/test_rules.py`

**Note:** Need to inject provinces into the YAML rules at runtime (or load dynamically).

**Phase:** Phase 1 (Core Infrastructure)

---

### 5. clinic_data.xlsx

**Current R Implementation:**
```r
# R/script3_create_table_clinic_static_data.R:9
clinic_data <- readxl::read_excel(
    path = here::here("reference_data", "clinic_data.xlsx"),
    sheet = 1,
    col_types = c("text", "text", ...)
)

# scripts/R/run_pipeline.R:77
download_google_sheet("1HOxi0o9fTAoHySjW_M3F-09TRBnUITOzzxGx2HwRMAw", "clinic_data.xlsx")
```

**Usage:** Creates clinic static data table in Script 3.

**Python Migration Strategy:**
- **Phase 3** (Table Creation) - not needed for initial phases
- Use `openpyxl` or `pl.read_excel()` to read
- Download from Google Sheets using `gspread` or manual download
- Lower priority - can be done later

**Files to Create (later):**
- `src/a4d/tables/clinic_static.py`

**Phase:** Phase 3 (Table Creation)

---

## Implementation Order

### Phase 1: Core Infrastructure (NEXT)

1. **Synonyms mapper** (high priority - needed for Script 1):
   - Create `src/a4d/synonyms/mapper.py`
   - Load YAML files
   - Rename Polars DataFrame columns
   - Tests

2. **Provinces loader** (high priority - needed for Script 2):
   - Create `src/a4d/schemas/provinces.py`
   - Load allowed provinces from YAML
   - Integrate with Pandera schemas

3. **Validation rules** (high priority - needed for Script 2):
   - Create `src/a4d/clean/rules.py`
   - Parse data_cleaning.yaml
   - Apply validation steps
   - Handle custom functions (extract_regimen, etc.)
   - Tests

### Phase 2+: Later

- Clinic data handling (Phase 3)

---

## Shared Reference Data

**IMPORTANT:** The reference_data/ folder is shared between R and Python:

```
a4d/
├── reference_data/          # SHARED
│   ├── synonyms/
│   ├── provinces/
│   └── data_cleaning.yaml
├── config.yml               # R only
├── R/                       # R pipeline
└── a4d-python/              # Python pipeline
    ├── .env                 # Python config (replaces config.yml)
    └── src/
```

Both pipelines read from the same reference_data/ folder. Do not modify these files without testing both pipelines!

---

## Testing Strategy

For each reference data module, create tests that:

1. **Load test** - Verify YAML/Excel files can be loaded
2. **Structure test** - Verify expected keys/columns exist
3. **Integration test** - Test with sample data

Example:
```python
# tests/test_synonyms/test_mapper.py
def test_patient_mapper_loads():
    mapper = ColumnMapper(Path("reference_data/synonyms/synonyms_patient.yaml"))
    assert "age" in mapper.synonyms
    assert "Age" in mapper._lookup

def test_patient_mapper_renames():
    mapper = ColumnMapper(Path("reference_data/synonyms/synonyms_patient.yaml"))
    df = pl.DataFrame({"Age": [25], "Patient ID": ["P001"]})
    df = mapper.rename_columns(df)
    assert "age" in df.columns
    assert "patient_id" in df.columns
```

---

## Summary

| Component | Priority | Complexity | Files to Create |
|-----------|----------|------------|-----------------|
| config.yml → Settings | ✅ Done | Low | Already done |
| Synonyms mapper | High | Low | mapper.py, tests |
| Provinces loader | High | Low | provinces.py, tests |
| Validation rules | High | Medium | rules.py, converters.py, tests |
| Clinic data | Low | Low | Later (Phase 3) |

**Next Step:** Start implementing synonyms/mapper.py in Phase 1.
