# Python Logging Options for BigQuery-Compatible JSON Logs

## Your Requirements

From the R pipeline experience:
1. ✅ **JSON formatted logs** - can be uploaded to BigQuery
2. ✅ **Structured fields** - fixed keys (level, message, file_name, patient_id, error_code, etc.)
3. ✅ **Simple to use** - not overly complex
4. ✅ **Context binding** - attach file/patient context to log messages
5. ✅ **File output** - write to log files

## Option Comparison

### 1. loguru (⭐ RECOMMENDED)

**Why it's better**:
- ✅ **Dead simple API** - one import, intuitive usage
- ✅ **JSON serialization built-in** - `serialize=True`
- ✅ **Context binding** - `logger.bind(patient_id=x)`
- ✅ **Beautiful console output** for development
- ✅ **File rotation** built-in
- ✅ **Popular and well-maintained** (17k+ GitHub stars)
- ✅ **Minimal configuration**

**Example**:
```python
from loguru import logger

# Configure once
logger.add(
    "logs/pipeline.log",
    format="{time} {level} {message}",
    serialize=True,  # JSON output
)

# Use anywhere - clean and simple
logger.info("Processing tracker", file="clinic_2024_01.xlsx", rows=100)

# Bind context (like R's with_file_logger)
file_logger = logger.bind(file_name="clinic_2024_01.xlsx")
file_logger.info("Processing patient", patient_id="PAT001")

# Errors with traceback
try:
    process_data()
except Exception as e:
    logger.exception("Processing failed")  # Auto-captures traceback
```

**JSON Output**:
```json
{
  "text": "Processing tracker",
  "record": {
    "elapsed": {"repr": "0:00:00.123456", "seconds": 0.123456},
    "exception": null,
    "extra": {"file": "clinic_2024_01.xlsx", "rows": 100},
    "file": {"name": "pipeline.py", "path": "/app/pipeline.py"},
    "function": "main",
    "level": {"icon": "ℹ️", "name": "INFO", "no": 20},
    "line": 42,
    "message": "Processing tracker",
    "module": "pipeline",
    "name": "__main__",
    "process": {"id": 12345, "name": "MainProcess"},
    "thread": {"id": 123456789, "name": "MainThread"},
    "time": {"repr": "2025-01-15 14:23:45.123456+00:00", "timestamp": 1737815025.123456}
  }
}
```

### 2. structlog (What I Initially Suggested)

**Why it's more complex**:
- ❌ **More configuration** - multiple processors to set up
- ❌ **Steeper learning curve** - less intuitive API
- ❌ **More boilerplate** - need to configure processors, wrappers, etc.
- ✅ **Very powerful** - but do you need all that power?

**Example**:
```python
import structlog

# Complex setup
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Usage
logger = structlog.get_logger()
logger.info("event", key="value")
```

**Verdict**: More power than you need, more complexity than you want.

### 3. python-json-logger (Lightweight)

**Why it might be too simple**:
- ✅ **Minimal** - just adds JSON formatting to stdlib logging
- ❌ **Less ergonomic** - still uses stdlib logging API (more verbose)
- ❌ **No built-in context binding**
- ✅ **Lightweight** - smallest dependency

**Example**:
```python
import logging
from pythonjsonlogger import jsonlogger

logger = logging.getLogger()
handler = logging.FileHandler("app.log")
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger.addHandler(handler)

# Usage (more verbose)
logger.info("Processing tracker", extra={"file": "clinic.xlsx", "rows": 100})
```

**Verdict**: Works but less convenient than loguru.

---

## Recommendation: Use loguru

For your use case, **loguru** is the sweet spot:
- Simple enough (cleaner than structlog)
- Powerful enough (JSON, context binding, file rotation)
- Well-maintained and popular
- Great documentation
- Beautiful development experience

## Implementation with loguru

### Configuration

**src/a4d/logging.py** (revised with loguru):
```python
from loguru import logger
from pathlib import Path
import sys
from a4d.config import settings


def setup_logging(log_dir: Path, log_name: str):
    """
    Configure loguru for the pipeline.

    Outputs:
    - JSON file logs (for BigQuery upload)
    - Pretty console logs (for development)
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"main_{log_name}.log"

    # Remove default handler
    logger.remove()

    # Add console handler (pretty output for development)
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )

    # Add file handler (JSON for BigQuery)
    logger.add(
        log_file,
        format="{time} {level} {message}",
        level="DEBUG",
        rotation="100 MB",  # Rotate when file gets large
        retention="30 days",  # Keep logs for 30 days
        compression="zip",  # Compress old logs
        serialize=True,  # JSON output - THIS IS KEY FOR BIGQUERY
    )

    logger.info(f"Logging initialized", log_file=str(log_file))


def get_logger(name: str = None):
    """
    Get a logger instance.

    For loguru, this just returns the global logger, but we keep
    the function for consistency with the R pattern.
    """
    if name:
        return logger.bind(module=name)
    return logger


# Context manager for file-specific logging (like R's with_file_logger)
from contextlib import contextmanager


@contextmanager
def file_logger(file_name: str, output_root: Path):
    """
    Context manager for file-specific logging.

    Equivalent to R's with_file_logger.
    """
    log_file = output_root / "logs" / f"{file_name}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Add a new sink for this specific file
    handler_id = logger.add(
        log_file,
        format="{time} {level} {message}",
        serialize=True,
        level="DEBUG",
    )

    # Bind file context
    bound_logger = logger.bind(file_name=file_name)

    try:
        yield bound_logger
    except Exception as e:
        bound_logger.exception("Processing failed", error_code="critical_abort")
        raise
    finally:
        # Remove the file-specific handler
        logger.remove(handler_id)
```

### Usage in Code

**Simple logging**:
```python
from a4d.logging import get_logger

logger = get_logger(__name__)

# Basic logging
logger.info("Processing started")

# With structured data (becomes JSON fields)
logger.info(
    "Found tracker files",
    count=156,
    root="/data/trackers"
)

# Warning
logger.warning(
    "Missing column",
    column="hba1c_updated_date",
    file="clinic_001.xlsx"
)

# Error with automatic traceback
try:
    process_data()
except Exception as e:
    logger.exception(
        "Processing failed",
        error_code="critical_abort",
        file_name="clinic_001.xlsx"
    )
```

**File-specific logging** (like R's `with_file_logger`):
```python
from a4d.logging import file_logger

with file_logger("clinic_001_patient", output_root) as log:
    log.info("Processing patient data")

    try:
        process_patient_data()
    except Exception as e:
        log.exception(
            "Patient processing failed",
            error_code="critical_abort"
        )
        # Automatically logged with traceback
```

**Context binding** (attach context to all subsequent logs):
```python
# Bind patient context
patient_logger = logger.bind(
    file_name="clinic_001.xlsx",
    patient_id="PAT001"
)

# All logs from this logger include patient context
patient_logger.info("Converting age")  # Includes patient_id in JSON
patient_logger.warning("Age out of range", value=250)  # Includes patient_id
```

### JSON Output for BigQuery

**Log file content** (automatically formatted as JSON):
```json
{
  "text": "Found tracker files",
  "record": {
    "time": {"timestamp": 1705329825.123},
    "level": {"name": "INFO"},
    "message": "Found tracker files",
    "extra": {
      "count": 156,
      "root": "/data/trackers"
    }
  }
}
```

### Upload to BigQuery

**scripts/upload_logs_to_bigquery.py**:
```python
import polars as pl
import json
from pathlib import Path
from google.cloud import bigquery
from a4d.config import settings

def parse_loguru_json(log_file: Path) -> pl.DataFrame:
    """Parse loguru JSON logs into BigQuery-ready DataFrame."""

    records = []

    with open(log_file) as f:
        for line in f:
            try:
                log = json.loads(line)
                record = log.get("record", {})

                # Extract fields for BigQuery
                records.append({
                    "timestamp": record.get("time", {}).get("timestamp"),
                    "level": record.get("level", {}).get("name"),
                    "message": record.get("message"),
                    "module": record.get("module"),
                    "function": record.get("function"),
                    "line": record.get("line"),

                    # Extract custom fields from 'extra'
                    "file_name": record.get("extra", {}).get("file_name"),
                    "patient_id": record.get("extra", {}).get("patient_id"),
                    "error_code": record.get("extra", {}).get("error_code"),
                    "count": record.get("extra", {}).get("count"),

                    # Exception info
                    "exception": record.get("exception", {}).get("type") if record.get("exception") else None,
                })
            except json.JSONDecodeError:
                continue

    return pl.DataFrame(records)


def upload_logs_to_bigquery():
    """Upload all log files to BigQuery logs table."""

    log_dir = settings.output_root / "logs"
    log_files = list(log_dir.glob("*.log"))

    # Parse all logs
    all_logs = pl.concat([parse_loguru_json(f) for f in log_files])

    # Upload to BigQuery
    client = bigquery.Client(project=settings.project_id)
    table_id = f"{settings.project_id}.{settings.dataset}.logs"

    all_logs.to_pandas().to_gbq(
        table_id,
        project_id=settings.project_id,
        if_exists="append",
    )

    print(f"Uploaded {len(all_logs)} log records to BigQuery")
```

### Migration from R Patterns

| R Pattern | loguru Equivalent |
|-----------|------------------|
| `logInfo(log_to_json("msg", values=list(x=1)))` | `logger.info("msg", x=1)` |
| `logWarn(...)` | `logger.warning(...)` |
| `logError(...)` | `logger.error(...)` |
| `with_file_logger(file, code)` | `with file_logger(file) as log: ...` |
| `setup_logger(dir, name)` | `setup_logging(dir, name)` |

---

## Performance Comparison

| Feature | loguru | structlog | python-json-logger |
|---------|--------|-----------|-------------------|
| **Ease of Use** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **JSON Output** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Context Binding** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **File Rotation** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| **Setup Complexity** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **Documentation** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **BigQuery Ready** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## Final Recommendation

**Use loguru** because it:
1. ✅ Does everything you need (JSON logs for BigQuery)
2. ✅ Much simpler than structlog
3. ✅ Clean, intuitive API
4. ✅ Great development experience (colored console logs)
5. ✅ Built-in features you'd have to add manually with others (rotation, compression)
6. ✅ Popular and well-maintained
7. ✅ Minimal configuration

**Update pyproject.toml**:
```toml
dependencies = [
    "loguru>=0.7.0",  # Instead of structlog
    # ... other deps
]
```

The migration will be smoother with loguru since it's more similar to simple logging patterns, while still giving you the structured JSON output you need for BigQuery.
