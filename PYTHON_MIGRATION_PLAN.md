# Python Migration - Detailed Technical Plan

This document provides detailed technical guidance for migrating each component of the A4D pipeline from R to Python.

## Table of Contents

1. [Foundation Setup](#foundation-setup)
2. [Configuration Management](#configuration-management)
3. [Logging Infrastructure](#logging-infrastructure)
4. [Synonym Mapping System](#synonym-mapping-system)
5. [Schema & Validation](#schema--validation)
6. [Script 1: Data Extraction](#script-1-data-extraction)
7. [Script 2: Data Cleaning](#script-2-data-cleaning)
8. [Script 3: Table Creation](#script-3-table-creation)
9. [GCP Integration](#gcp-integration)
10. [Testing Strategy](#testing-strategy)
11. [Migration Checklist](#migration-checklist)

---

## Foundation Setup

### Project Initialization

```bash
# Create new Python project
mkdir a4d-python
cd a4d-python

# Initialize with uv (recommended)
uv init

# Create project structure
mkdir -p src/a4d/{config,logging,schemas,synonyms,extract,clean,tables,gcp,utils}
mkdir -p tests/{test_extract,test_clean,test_tables,comparison}
mkdir -p scripts
mkdir -p reference_data/{synonyms,provinces}
```

### pyproject.toml

```toml
[project]
name = "a4d"
version = "0.1.0"
description = "A4D Medical Tracker Data Processing Pipeline"
requires-python = ">=3.11"
dependencies = [
    "polars>=0.20.0",
    "duckdb>=0.10.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.2.0",
    "pandera[polars]>=0.18.0",
    "structlog>=24.1.0",
    "openpyxl>=3.1.0",
    "google-cloud-bigquery>=3.17.0",
    "google-cloud-storage>=2.14.0",
    "pyyaml>=6.0",
    "prefect>=2.14.0",  # or use doit
    "typer>=0.9.0",
    "rich>=13.7.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.2.0",
    "mypy>=1.8.0",
    "pre-commit>=3.6.0",
]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W", "UP", "B", "A", "C4", "PT"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN pip install uv && \
    uv sync --frozen

# Copy application code
COPY src/ src/
COPY scripts/ scripts/
COPY reference_data/ reference_data/

# Set environment
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

CMD ["python", "scripts/run_pipeline.py"]
```

---

## Configuration Management

### R Pattern
```r
# config.yml
config <- config::get()
data_dir <- config$data_root
```

### Python Implementation

**src/a4d/config.py**:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Literal


class Settings(BaseSettings):
    """Application configuration with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="A4D_",
        case_sensitive=False,
    )

    # Environment
    environment: Literal["development", "production"] = "development"

    # GCP Configuration
    download_bucket: str = "a4dphase2_upload"
    upload_bucket: str = "a4dphase2_output"
    project_id: str = "a4dphase2"
    dataset: str = "tracker"

    # Paths
    data_root: Path = Path("/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload")
    output_dir: Path = Path("output")

    # Processing settings
    max_workers: int = 4
    batch_size: int = 100

    # Error values (matching R constants)
    error_val_numeric: float = 999999.0
    error_val_character: str = "Undefined"
    error_val_date: str = "9999-09-09"

    @property
    def output_root(self) -> Path:
        """Computed output root path."""
        return self.data_root / self.output_dir

    @property
    def tracker_root(self) -> Path:
        """Tracker files root directory."""
        return self.data_root


# Global settings instance
settings = Settings()
```

**Usage**:
```python
from a4d.config import settings

print(settings.data_root)
print(settings.project_id)
```

**.env.example**:
```bash
A4D_ENVIRONMENT=development
A4D_DATA_ROOT=/path/to/data
A4D_PROJECT_ID=a4dphase2
A4D_DOWNLOAD_BUCKET=a4dphase2_upload
```

---

## Logging Infrastructure

### R Pattern
```r
setup_logger <- function(output_dir, log_name) {
    logger <- createLogger(...)
    registerLogger(logger)
}

logInfo(log_to_json("Message", values = list(...)))
```

### Python Implementation

**src/a4d/logging.py**:
```python
import structlog
from pathlib import Path
from typing import Any
import sys


def setup_logging(log_dir: Path, log_name: str, level: str = "INFO") -> None:
    """Configure structured logging."""

    log_file = log_dir / f"main_{log_name}.log"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Processors for structured logging
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Development: human-readable console output
    # Production: JSON file output
    if log_file:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Add file handler
    import logging
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance with bound context."""
    return structlog.get_logger(name)


# Context manager for file-specific logging
from contextlib import contextmanager

@contextmanager
def file_logger(file_name: str, output_root: Path):
    """Context manager for file-specific logging (like R's with_file_logger)."""

    log_file = output_root / "logs" / f"{file_name}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = get_logger(file_name)
    logger = logger.bind(file_name=file_name)

    try:
        yield logger
    except Exception as e:
        logger.error(
            "Processing failed",
            error=str(e),
            error_code="critical_abort",
            exc_info=True,
        )
        raise
```

**Usage**:
```python
from a4d.logging import setup_logging, get_logger, file_logger
from a4d.config import settings

# Setup main logger
setup_logging(settings.output_root / "logs", "script1")

# Get logger
logger = get_logger(__name__)
logger.info("Processing started", tracker_count=10, root=str(settings.data_root))

# File-specific logging
with file_logger("clinic_2024_01_patient", settings.output_root) as log:
    log.info("Processing patient data")
    log.warning("Missing column detected", column="hba1c_updated_date")
```

---

## Synonym Mapping System

### R Pattern
```r
# Read from YAML
synonyms <- read_column_synonyms("synonyms_patient.yaml")

# Match columns
col_match <- synonyms %>%
    filter(tracker_name %in% colnames(df))
```

### Python Implementation

**src/a4d/synonyms/mapper.py**:
```python
import yaml
from pathlib import Path
from typing import Dict, List
import polars as pl
from functools import lru_cache


class SynonymMapper:
    """Maps varying column names to standardized names using YAML config."""

    def __init__(self, synonym_file: Path):
        self.synonym_file = synonym_file
        self._mapping = self._load_synonyms()

    def _load_synonyms(self) -> Dict[str, str]:
        """Load synonyms from YAML and create reverse mapping."""
        with open(self.synonym_file) as f:
            synonyms = yaml.safe_load(f)

        # Create reverse mapping: synonym -> standard_name
        mapping = {}
        for standard_name, variants in synonyms.items():
            if isinstance(variants, list):
                for variant in variants:
                    mapping[variant.lower()] = standard_name
            else:
                mapping[variants.lower()] = standard_name

        return mapping

    def map_columns(self, columns: List[str]) -> Dict[str, str]:
        """
        Map DataFrame columns to standard names.

        Returns dict: {original_col: standard_col}
        """
        result = {}
        for col in columns:
            col_lower = col.lower().strip()
            standard = self._mapping.get(col_lower, col)
            result[col] = standard
        return result

    def rename_dataframe(self, df: pl.DataFrame) -> pl.DataFrame:
        """Rename DataFrame columns using synonym mapping."""
        mapping = self.map_columns(df.columns)
        return df.rename(mapping)

    def get_missing_required(
        self, columns: List[str], required: List[str]
    ) -> List[str]:
        """Check which required columns are missing after mapping."""
        mapped = set(self.map_columns(columns).values())
        return [col for col in required if col not in mapped]


@lru_cache(maxsize=2)
def get_synonym_mapper(data_type: str) -> SynonymMapper:
    """Get cached synonym mapper for patient or product data."""
    synonym_file = Path(f"reference_data/synonyms/synonyms_{data_type}.yaml")
    return SynonymMapper(synonym_file)
```

**Usage**:
```python
from a4d.synonyms.mapper import get_synonym_mapper

# Load mapper
mapper = get_synonym_mapper("patient")

# Map columns
df = pl.read_excel("tracker.xlsx", sheet_name="2024-01")
df = mapper.rename_dataframe(df)

# Check missing
required = ["patient_id", "tracker_year", "tracker_month"]
missing = mapper.get_missing_required(df.columns, required)
if missing:
    logger.warning("Missing required columns", missing=missing)
```

---

## Schema & Validation

### R Pattern
```r
# Define schema as tibble
schema <- tibble(
    age = integer(),
    hba1c_baseline = numeric(),
    dob = lubridate::as_date(1),
    ...
)

# Apply validation inline
df <- df %>%
    mutate(
        across(numeric_cols, \(x) convert_to(x, as.numeric, ERROR_VAL))
    )
```

### Python Implementation

**src/a4d/schemas/patient.py**:
```python
from pydantic import BaseModel, Field, field_validator
from datetime import date
from typing import Optional, Literal
import polars as pl
import pandera.polars as pa
from a4d.config import settings


# Pydantic model for row-level validation (if needed)
class PatientRecord(BaseModel):
    """Single patient record validation."""

    patient_id: str
    clinic_id: str
    tracker_year: int = Field(ge=2018, le=2026)
    tracker_month: int = Field(ge=1, le=12)
    tracker_date: date

    age: Optional[int] = Field(None, ge=0, le=25)
    sex: Optional[Literal["M", "F"]] = None
    dob: Optional[date] = None

    hba1c_baseline: Optional[float] = Field(None, ge=4.0, le=18.0)
    hba1c_updated: Optional[float] = Field(None, ge=4.0, le=18.0)

    # ... more fields


# Pandera schema for DataFrame validation (preferred)
class PatientSchema(pa.DataFrameModel):
    """DataFrame schema for patient data."""

    patient_id: str = pa.Field(nullable=False)
    clinic_id: str = pa.Field(nullable=False)
    tracker_year: int = pa.Field(ge=2018, le=2026, nullable=False)
    tracker_month: int = pa.Field(ge=1, le=12, nullable=False)
    tracker_date: date = pa.Field(nullable=False)

    age: int = pa.Field(ge=0, le=25, nullable=True)
    sex: str = pa.Field(isin=["M", "F"], nullable=True)
    dob: date = pa.Field(nullable=True)

    hba1c_baseline: float = pa.Field(ge=4.0, le=18.0, nullable=True)
    hba1c_updated: float = pa.Field(ge=4.0, le=18.0, nullable=True)
    hba1c_baseline_exceeds: bool = pa.Field(nullable=True)
    hba1c_updated_exceeds: bool = pa.Field(nullable=True)

    blood_pressure_sys_mmhg: int = pa.Field(nullable=True)
    blood_pressure_dias_mmhg: int = pa.Field(nullable=True)

    status: str = pa.Field(nullable=True)
    support_level: str = pa.Field(nullable=True)

    # Add all fields from R schema...

    class Config:
        strict = False  # Allow extra columns initially
        coerce = True   # Try to coerce types


def validate_patient_dataframe(df: pl.DataFrame) -> pl.DataFrame:
    """Validate patient DataFrame against schema."""
    try:
        # Convert to pandas for pandera validation
        # (pandera-polars is experimental, use pandas bridge)
        df_pd = df.to_pandas()
        validated = PatientSchema.validate(df_pd)
        return pl.from_pandas(validated)
    except pa.errors.SchemaError as e:
        logger.error("Schema validation failed", error=str(e))
        raise
```

**src/a4d/schemas/validation.py** (YAML-based validation):
```python
import yaml
from pathlib import Path
from typing import Any, List, Dict
import polars as pl
from a4d.logging import get_logger

logger = get_logger(__name__)


class ColumnValidator:
    """Validate columns based on YAML configuration."""

    def __init__(self, config_path: Path):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

    def validate_column(
        self, df: pl.DataFrame, column: str, error_value: Any
    ) -> pl.DataFrame:
        """Apply validation rules from YAML config to a column."""

        if column not in self.config:
            return df

        rules = self.config[column].get("steps", [])

        for rule in rules:
            rule_type = rule["type"]

            if rule_type == "allowed_values":
                allowed = rule["allowed_values"]
                replace_invalid = rule.get("replace_invalid", False)

                if replace_invalid:
                    df = df.with_columns(
                        pl.when(pl.col(column).is_in(allowed))
                        .then(pl.col(column))
                        .otherwise(error_value)
                        .alias(column)
                    )
                else:
                    # Log invalid values but don't replace
                    invalid = df.filter(~pl.col(column).is_in(allowed))
                    if len(invalid) > 0:
                        logger.warning(
                            "Invalid values found",
                            column=column,
                            invalid_count=len(invalid),
                            allowed=allowed,
                        )

            elif rule_type == "basic_function":
                func_name = rule["function_name"]
                # Apply custom function (implement as needed)
                pass

        return df

    def validate_dataframe(self, df: pl.DataFrame) -> pl.DataFrame:
        """Validate all configured columns in DataFrame."""
        for column in df.columns:
            if column in self.config:
                df = self.validate_column(df, column, None)
        return df


# Global validator instance
_validator = None

def get_validator() -> ColumnValidator:
    global _validator
    if _validator is None:
        config_path = Path("reference_data/data_cleaning.yaml")
        _validator = ColumnValidator(config_path)
    return _validator
```

---

## Script 1: Data Extraction

### R → Python Migration

**R Code** (script1_process_patient_data.R):
```r
df_raw <- readxl::read_excel(
    path = tracker_file,
    sheet = sheet_name,
    col_types = "text"
)

# Apply synonym mapping
for (i in seq_len(nrow(synonyms))) {
    colnames(df_raw) <- sub(synonyms$tracker_name[i],
                            synonyms$variable_name[i],
                            colnames(df_raw))
}
```

**Python Code** (src/a4d/extract/patient.py):
```python
import polars as pl
from pathlib import Path
from typing import Dict, List
from a4d.synonyms.mapper import get_synonym_mapper
from a4d.logging import get_logger

logger = get_logger(__name__)


def extract_patient_data_from_sheet(
    tracker_file: Path,
    sheet_name: str,
) -> pl.DataFrame:
    """
    Extract patient data from Excel sheet.

    Equivalent to R's process_tracker_patient_data.
    """

    # Read Excel with Polars (fast) or fallback to openpyxl
    try:
        df = pl.read_excel(
            tracker_file,
            sheet_name=sheet_name,
            read_csv_options={"infer_schema_length": 0},  # Read as strings
        )
    except Exception as e:
        logger.warning(
            "Polars read failed, using openpyxl",
            file=str(tracker_file),
            sheet=sheet_name,
            error=str(e),
        )
        import openpyxl
        wb = openpyxl.load_workbook(tracker_file, read_only=True, data_only=True)
        ws = wb[sheet_name]
        data = [[cell.value for cell in row] for row in ws.iter_rows()]
        df = pl.DataFrame(data[1:], schema=data[0], orient="row")

    # Apply synonym mapping
    mapper = get_synonym_mapper("patient")
    df = mapper.rename_dataframe(df)

    # Add metadata columns
    df = df.with_columns([
        pl.lit(sheet_name).alias("sheet_name"),
        pl.lit(tracker_file.name).alias("file_name"),
    ])

    logger.info(
        "Extracted patient data",
        file=str(tracker_file),
        sheet=sheet_name,
        rows=len(df),
        columns=len(df.columns),
    )

    return df


def process_tracker_patient_data(
    tracker_file: Path,
    output_root: Path,
) -> None:
    """
    Process all patient sheets in a tracker file.

    Equivalent to R's process_tracker_patient_data.
    """

    import openpyxl

    wb = openpyxl.load_workbook(tracker_file, read_only=True)
    patient_sheets = [s for s in wb.sheetnames if s.startswith("20")]

    all_data = []

    for sheet_name in patient_sheets:
        try:
            df = extract_patient_data_from_sheet(tracker_file, sheet_name)
            all_data.append(df)
        except Exception as e:
            logger.error(
                "Failed to process sheet",
                file=str(tracker_file),
                sheet=sheet_name,
                error=str(e),
                error_code="sheet_processing_error",
                exc_info=True,
            )

    if not all_data:
        logger.warning("No patient data extracted", file=str(tracker_file))
        return

    # Concatenate all sheets
    df_combined = pl.concat(all_data, how="diagonal")  # Allows different schemas

    # Export as Parquet
    output_file = output_root / f"{tracker_file.stem}_patient_raw.parquet"
    df_combined.write_parquet(output_file, compression="zstd")

    logger.info(
        "Exported patient data",
        file=str(output_file),
        rows=len(df_combined),
    )
```

**src/a4d/extract/product.py** (similar pattern for product data)

**scripts/run_script_1.py**:
```python
#!/usr/bin/env python3
from pathlib import Path
import typer
from rich.progress import Progress
from a4d.config import settings
from a4d.logging import setup_logging, get_logger
from a4d.extract.patient import process_tracker_patient_data
from a4d.extract.product import process_tracker_product_data

app = typer.Typer()
logger = get_logger(__name__)


@app.command()
def main():
    """Extract raw data from Excel tracker files."""

    # Initialize paths
    output_root = settings.output_root
    patient_data_raw = output_root / "patient_data_raw"
    product_data_raw = output_root / "product_data_raw"

    patient_data_raw.mkdir(parents=True, exist_ok=True)
    product_data_raw.mkdir(parents=True, exist_ok=True)

    # Setup logging
    setup_logging(output_root / "logs", "script1")

    # Get tracker files
    tracker_files = list(settings.tracker_root.rglob("*.xlsx"))
    tracker_files = [f for f in tracker_files if not f.name.startswith("~")]

    logger.info(
        "Found tracker files",
        count=len(tracker_files),
        root=str(settings.tracker_root),
    )

    # Process each tracker file
    with Progress() as progress:
        task = progress.add_task("Processing trackers...", total=len(tracker_files))

        for tracker_file in tracker_files:
            logger.info("Processing tracker", file=str(tracker_file))

            try:
                process_tracker_patient_data(tracker_file, patient_data_raw)
                process_tracker_product_data(tracker_file, product_data_raw)
            except Exception as e:
                logger.error(
                    "Failed to process tracker",
                    file=str(tracker_file),
                    error=str(e),
                    error_code="critical_abort",
                    exc_info=True,
                )

            progress.advance(task)

    logger.info("Script 1 completed")


if __name__ == "__main__":
    app()
```

---

## Script 2: Data Cleaning

### Key Challenge: Row-wise Operations

**R Code** (heavy use of rowwise):
```r
df_patient <- df_patient %>%
    dplyr::rowwise() %>%
    dplyr::mutate(
        height = transform_cm_to_m(height),
        age = fix_age(age, dob, tracker_year, tracker_month, patient_id),
        ...
    )
```

**Python Code** - Vectorized Approach:
```python
def fix_age_vectorized(
    age: pl.Series,
    dob: pl.Series,
    tracker_year: pl.Series,
    tracker_month: pl.Series,
) -> pl.Series:
    """
    Fix age values (vectorized version of R's fix_age).

    Calculate age from DOB if age is invalid.
    """
    from datetime import date

    # Create tracker date
    tracker_date = pl.date(tracker_year, tracker_month, 1)

    # Calculate age from DOB
    calculated_age = (
        (tracker_date.dt.year() - dob.dt.year()) -
        ((tracker_date.dt.month() < dob.dt.month()) |
         ((tracker_date.dt.month() == dob.dt.month()) &
          (tracker_date.dt.day() < dob.dt.day())))
    )

    # Use calculated age if provided age is invalid
    return pl.when(
        (age.is_null()) | (age < 0) | (age > 25)
    ).then(calculated_age).otherwise(age)


# Apply in DataFrame
df = df.with_columns([
    fix_age_vectorized(
        pl.col("age"),
        pl.col("dob"),
        pl.col("tracker_year"),
        pl.col("tracker_month"),
    ).alias("age"),
])
```

**src/a4d/clean/patient.py**:
```python
import polars as pl
from pathlib import Path
from a4d.config import settings
from a4d.schemas.validation import get_validator
from a4d.logging import get_logger

logger = get_logger(__name__)


def extract_date_from_measurement(df: pl.DataFrame, col: str) -> pl.DataFrame:
    """
    Extract date from measurement column (e.g., '7.5 (2023-01-15)').

    Equivalent to R's extract_date_from_measurement.
    """
    date_col = f"{col}_date"

    df = df.with_columns([
        # Extract date part using regex
        pl.col(col)
        .str.extract(r"\(([0-9]{4}-[0-9]{2}-[0-9]{2})\)", 1)
        .str.to_date(strict=False)
        .alias(date_col),

        # Extract numeric part
        pl.col(col)
        .str.extract(r"^([0-9.]+)", 1)
        .cast(pl.Float64, strict=False)
        .alias(col),
    ])

    return df


def split_bp_in_sys_and_dias(df: pl.DataFrame) -> pl.DataFrame:
    """Split blood_pressure_mmhg column into sys and dias."""

    df = df.with_columns([
        pl.col("blood_pressure_mmhg")
        .str.split("/")
        .list.get(0)
        .cast(pl.Int32, strict=False)
        .alias("blood_pressure_sys_mmhg"),

        pl.col("blood_pressure_mmhg")
        .str.split("/")
        .list.get(1)
        .cast(pl.Int32, strict=False)
        .alias("blood_pressure_dias_mmhg"),
    ])

    return df


def process_raw_patient_file(
    patient_file: Path,
    output_root: Path,
) -> None:
    """
    Clean and validate raw patient data.

    Equivalent to R's process_raw_patient_file.
    """

    # Read raw data
    df = pl.read_parquet(patient_file)

    logger.info("Processing raw patient data", file=str(patient_file), rows=len(df))

    # --- TRANSFORMATIONS ---

    # Handle legacy date formats
    if "hba1c_updated_date" not in df.columns and "hba1c_updated" in df.columns:
        logger.warning("Extracting date from hba1c_updated column")
        df = extract_date_from_measurement(df, "hba1c_updated")

    if "fbg_updated_date" not in df.columns and "fbg_updated_mg" in df.columns:
        logger.warning("Extracting date from fbg_updated_mg column")
        df = extract_date_from_measurement(df, "fbg_updated_mg")

    # Split blood pressure
    if "blood_pressure_mmhg" in df.columns:
        df = split_bp_in_sys_and_dias(df)

    # Detect exceeds indicators
    df = df.with_columns([
        pl.col("hba1c_baseline").str.contains(r"[<>]").alias("hba1c_baseline_exceeds"),
        pl.col("hba1c_updated").str.contains(r"[<>]").alias("hba1c_updated_exceeds"),
    ])

    # Handle insulin columns (2024+ format)
    if "human_insulin_pre_mixed" in df.columns:
        df = df.with_columns([
            # Determine insulin type
            pl.when(
                pl.col("human_insulin_pre_mixed").eq("Y") |
                pl.col("human_insulin_short_acting").eq("Y") |
                pl.col("human_insulin_intermediate_acting").eq("Y")
            )
            .then(pl.lit("human insulin"))
            .otherwise(pl.lit("analog insulin"))
            .alias("insulin_type"),

            # Build insulin subtype list
            pl.concat_list([
                pl.when(pl.col("human_insulin_pre_mixed").eq("Y"))
                  .then(pl.lit("pre-mixed")).otherwise(None),
                pl.when(pl.col("human_insulin_short_acting").eq("Y"))
                  .then(pl.lit("short-acting")).otherwise(None),
                pl.when(pl.col("human_insulin_intermediate_acting").eq("Y"))
                  .then(pl.lit("intermediate-acting")).otherwise(None),
                pl.when(pl.col("analog_insulin_rapid_acting").eq("Y"))
                  .then(pl.lit("rapid-acting")).otherwise(None),
                pl.when(pl.col("analog_insulin_long_acting").eq("Y"))
                  .then(pl.lit("long-acting")).otherwise(None),
            ])
            .list.drop_nulls()
            .list.join(",")
            .alias("insulin_subtype"),
        ])

    # --- TYPE CONVERSION & VALIDATION ---

    # Apply schema (coerce types)
    df = coerce_to_schema(df)

    # Apply YAML validation rules
    validator = get_validator()
    df = validator.validate_dataframe(df)

    # Apply custom fixes (vectorized)
    df = apply_patient_fixes(df)

    # --- EXPORT ---

    output_file = output_root / patient_file.name.replace("_patient_raw", "_patient_cleaned")
    df.write_parquet(output_file, compression="zstd")

    logger.info("Exported cleaned patient data", file=str(output_file), rows=len(df))


def coerce_to_schema(df: pl.DataFrame) -> pl.DataFrame:
    """Coerce DataFrame to target schema with error handling."""

    type_mapping = {
        # Numeric fields
        "age": pl.Int32,
        "hba1c_baseline": pl.Float64,
        "hba1c_updated": pl.Float64,
        "fbg_baseline_mg": pl.Float64,
        # ... add all fields

        # Date fields
        "dob": pl.Date,
        "recruitment_date": pl.Date,
        "tracker_date": pl.Date,

        # Boolean fields
        "hba1c_baseline_exceeds": pl.Boolean,
        "hba1c_updated_exceeds": pl.Boolean,
    }

    for col, dtype in type_mapping.items():
        if col in df.columns:
            df = df.with_columns([
                pl.col(col).cast(dtype, strict=False).alias(col)
            ])

    return df


def apply_patient_fixes(df: pl.DataFrame) -> pl.DataFrame:
    """Apply all patient data fixes (vectorized)."""

    df = df.with_columns([
        # Remove < > from HbA1c
        pl.col("hba1c_baseline").str.replace_all(r"[<>]", ""),
        pl.col("hba1c_updated").str.replace_all(r"[<>]", ""),

        # Transform height from cm to m
        pl.when(pl.col("height") > 2.5)
          .then(pl.col("height") / 100)
          .otherwise(pl.col("height"))
          .alias("height"),

        # Clip height
        pl.col("height").clip(0.0, 2.3).alias("height"),

        # Clip weight
        pl.col("weight").clip(0.0, 200.0).alias("weight"),

        # Calculate BMI
        (pl.col("weight") / (pl.col("height") ** 2))
          .clip(4.0, 60.0)
          .alias("bmi"),

        # Fix age
        fix_age_vectorized(
            pl.col("age"),
            pl.col("dob"),
            pl.col("tracker_year"),
            pl.col("tracker_month"),
        ).alias("age"),
    ])

    # Calculate tracker_date from year and month
    df = df.with_columns([
        pl.date(pl.col("tracker_year"), pl.col("tracker_month"), 1).alias("tracker_date")
    ])

    return df
```

---

## Script 3: Table Creation

**scripts/run_script_3.py**:
```python
#!/usr/bin/env python3
import polars as pl
from pathlib import Path
from a4d.config import settings
from a4d.logging import setup_logging, get_logger
from a4d.tables.patient import (
    create_table_patient_data_static,
    create_table_patient_data_monthly,
    create_table_patient_data_annual,
)
from a4d.tables.product import create_table_product_data
from a4d.tables.clinic import create_table_clinic_static_data

logger = get_logger(__name__)


def main():
    """Create final database tables."""

    output_root = settings.output_root
    tables_dir = output_root / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    setup_logging(output_root / "logs", "script3")

    # Get cleaned data files
    patient_files = list((output_root / "patient_data_cleaned").glob("*.parquet"))
    product_files = list((output_root / "product_data_cleaned").glob("*.parquet"))

    logger.info("Found cleaned files", patient=len(patient_files), product=len(product_files))

    # Create tables
    create_table_patient_data_static(patient_files, tables_dir)
    create_table_patient_data_monthly(patient_files, tables_dir)
    create_table_patient_data_annual(patient_files, tables_dir)
    create_table_product_data(product_files, tables_dir)
    create_table_clinic_static_data(tables_dir)

    logger.info("Script 3 completed")


if __name__ == "__main__":
    main()
```

**src/a4d/tables/patient.py**:
```python
import polars as pl
from pathlib import Path
from typing import List
from a4d.logging import get_logger

logger = get_logger(__name__)


def create_table_patient_data_static(
    patient_files: List[Path],
    output_dir: Path,
) -> None:
    """
    Create static patient data table.

    Contains one row per patient with time-invariant attributes.
    """

    # Read all patient data
    df = pl.concat([pl.read_parquet(f) for f in patient_files])

    # Select static columns
    static_cols = [
        "patient_id",
        "clinic_id",
        "name",
        "sex",
        "dob",
        "recruitment_date",
        "t1d_diagnosis_date",
        "t1d_diagnosis_age",
        "t1d_diagnosis_with_dka",
        "family_history",
    ]

    # Keep most recent record per patient
    df_static = (
        df
        .select(static_cols)
        .sort("tracker_date", descending=True)
        .unique(subset=["patient_id"], keep="first")
    )

    output_file = output_dir / "patient_data_static.parquet"
    df_static.write_parquet(output_file, compression="zstd")

    logger.info("Created static patient table", file=str(output_file), rows=len(df_static))


def create_table_patient_data_monthly(
    patient_files: List[Path],
    output_dir: Path,
) -> None:
    """
    Create monthly patient data table.

    Contains time-varying attributes tracked monthly.
    """

    # Use DuckDB for complex deduplication logic
    import duckdb

    # Read all patient data
    df = pl.concat([pl.read_parquet(f) for f in patient_files])

    # Use DuckDB to identify changes
    query = """
    SELECT *,
        LAG(hba1c_updated) OVER (PARTITION BY patient_id ORDER BY tracker_date) as prev_hba1c,
        LAG(status) OVER (PARTITION BY patient_id ORDER BY tracker_date) as prev_status
    FROM df
    WHERE
        -- Keep if values changed from previous month
        hba1c_updated IS DISTINCT FROM prev_hba1c
        OR status IS DISTINCT FROM prev_status
        -- Or if it's the first record
        OR prev_hba1c IS NULL
    """

    df_monthly = duckdb.query(query).pl()

    # Remove helper columns
    df_monthly = df_monthly.drop(["prev_hba1c", "prev_status"])

    output_file = output_dir / "patient_data_monthly.parquet"
    df_monthly.write_parquet(output_file, compression="zstd")

    logger.info("Created monthly patient table", file=str(output_file), rows=len(df_monthly))
```

---

## GCP Integration

**src/a4d/gcp/bigquery.py**:
```python
from google.cloud import bigquery
from pathlib import Path
from a4d.config import settings
from a4d.logging import get_logger

logger = get_logger(__name__)


def ingest_table(
    table_name: str,
    source_file: Path,
    clustering_fields: list[str],
) -> None:
    """
    Ingest Parquet file to BigQuery table.

    Replaces R's system("bq load ...") calls.
    """

    client = bigquery.Client(project=settings.project_id)

    # Delete old table
    table_id = f"{settings.project_id}.{settings.dataset}.{table_name}"
    try:
        client.delete_table(table_id)
        logger.info("Deleted old table", table=table_id)
    except Exception:
        pass  # Table doesn't exist

    # Configure load job
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        clustering_fields=clustering_fields,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    # Load data
    with open(source_file, "rb") as f:
        job = client.load_table_from_file(f, table_id, job_config=job_config)

    # Wait for completion
    job.result()

    # Get table info
    table = client.get_table(table_id)

    logger.info(
        "Ingested table to BigQuery",
        table=table_id,
        rows=table.num_rows,
        size_mb=table.num_bytes / 1024 / 1024,
    )
```

**src/a4d/gcp/storage.py**:
```python
from google.cloud import storage
from pathlib import Path
from a4d.config import settings
from a4d.logging import get_logger

logger = get_logger(__name__)


def download_bucket(bucket_name: str, dest_dir: Path) -> None:
    """Download all files from GCS bucket."""

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    blobs = bucket.list_blobs()

    for blob in blobs:
        dest_path = dest_dir / blob.name
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        blob.download_to_filename(dest_path)
        logger.info("Downloaded file", blob=blob.name, dest=str(dest_path))


def upload_directory(source_dir: Path, bucket_name: str) -> None:
    """Upload directory to GCS bucket."""

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    for file_path in source_dir.rglob("*"):
        if file_path.is_file():
            blob_name = str(file_path.relative_to(source_dir))
            blob = bucket.blob(blob_name)

            blob.upload_from_filename(file_path)
            logger.info("Uploaded file", file=str(file_path), blob=blob_name)
```

---

## Testing Strategy

**tests/comparison/test_output_equivalence.py**:
```python
import polars as pl
import pytest
from pathlib import Path


def compare_parquet_files(r_file: Path, py_file: Path, tolerance: float = 1e-6):
    """Compare Parquet files from R and Python pipelines."""

    r_df = pl.read_parquet(r_file).sort(by=r_df.columns[0])
    py_df = pl.read_parquet(py_file).sort(by=py_df.columns[0])

    # Compare schemas
    assert set(r_df.columns) == set(py_df.columns), "Column mismatch"

    # Compare row counts
    assert len(r_df) == len(py_df), f"Row count mismatch: {len(r_df)} vs {len(py_df)}"

    # Compare values
    for col in r_df.columns:
        r_col = r_df[col]
        py_col = py_df[col]

        if r_col.dtype in [pl.Float32, pl.Float64]:
            # Numeric comparison with tolerance
            diff = (r_col - py_col).abs()
            assert diff.max() < tolerance, f"Numeric difference in {col}"
        else:
            # Exact comparison
            assert r_col.equals(py_col), f"Difference in {col}"


@pytest.mark.parametrize("file_name", [
    "clinic_2024_01_patient_cleaned.parquet",
    # Add more files
])
def test_script2_output(file_name):
    """Test Script 2 output matches R pipeline."""

    r_file = Path("output_r/patient_data_cleaned") / file_name
    py_file = Path("output_python/patient_data_cleaned") / file_name

    compare_parquet_files(r_file, py_file)
```

---

## Migration Checklist

### Phase 0: Foundation ✓
- [ ] Create Python project structure
- [ ] Set up dependency management (uv/Poetry)
- [ ] Configure Dockerfile
- [ ] Set up CI/CD (GitHub Actions)
- [ ] Create comparison utilities
- [ ] Set up pre-commit hooks

### Phase 1: Infrastructure ✓
- [ ] Configuration management (Pydantic)
- [ ] Logging (structlog)
- [ ] Synonym mapper
- [ ] Validation schemas (Pandera)
- [ ] GCP utilities
- [ ] Path utilities

### Phase 2: Script 1 ✓
- [ ] Excel reading
- [ ] Patient data extraction
- [ ] Product data extraction
- [ ] CLI script
- [ ] Unit tests
- [ ] **Compare outputs with R**

### Phase 3: Script 2 ✓
- [ ] Type conversion
- [ ] Validation logic
- [ ] Custom fixes (vectorized)
- [ ] CLI script
- [ ] Unit tests
- [ ] **Compare outputs with R**

### Phase 4: Script 3 ✓
- [ ] Static patient table
- [ ] Monthly patient table
- [ ] Annual patient table
- [ ] Product table
- [ ] Clinic table
- [ ] Product-patient linking
- [ ] **Compare outputs with R**

### Phase 5: Orchestration ✓
- [ ] Pipeline orchestration (Prefect/doit)
- [ ] BigQuery ingestion
- [ ] GCS upload/download
- [ ] End-to-end script
- [ ] Deployment config

### Phase 6: Validation ✓
- [ ] Run both pipelines in parallel
- [ ] Automated comparison
- [ ] Performance benchmarks
- [ ] Bug fixes

### Phase 7: Transition ✓
- [ ] Documentation
- [ ] Team training
- [ ] Production deployment
- [ ] Monitoring setup
- [ ] R pipeline deprecation

---

## Performance Optimization Tips

1. **Use Lazy Evaluation**:
```python
# Lazy (efficient)
df = (
    pl.scan_parquet("*.parquet")
    .filter(pl.col("tracker_year") == 2024)
    .group_by("patient_id")
    .agg(pl.col("hba1c_updated").mean())
    .collect()  # Execute here
)
```

2. **Parallel Processing**:
```python
from concurrent.futures import ProcessPoolExecutor

with ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(process_file, tracker_files))
```

3. **Use DuckDB for Complex Joins**:
```python
import duckdb

# More efficient than Polars for complex SQL
result = duckdb.query("""
    SELECT p.*, c.clinic_name
    FROM 'patient_*.parquet' p
    JOIN 'clinic.parquet' c ON p.clinic_id = c.clinic_id
    WHERE p.tracker_year = 2024
""").pl()
```

4. **Streaming for Large Files**:
```python
# Stream processing for memory efficiency
for batch in pl.read_parquet_batched("large_file.parquet", batch_size=10000):
    process_batch(batch)
```

---

This technical plan provides a complete blueprint for the R to Python migration. Each section can be implemented incrementally while validating against the R pipeline at each step.
