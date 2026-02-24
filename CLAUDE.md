# CLAUDE.md

This repository contains **two projects**:

## 1. R Pipeline (Production - Legacy)

**Location**: Root directory
**Status**: Production (being phased out)

The original R implementation of the A4D medical tracker data processing pipeline.

**Key Files**:
- `R/` - R package code
- `scripts/R/` - Pipeline scripts
- `reference_data/` - Shared YAML configurations

**Commands**: See README.md for R-specific commands

---

## 2. Python Pipeline (Active Development)

**Location**: `a4d-python/`
**Status**: Active migration
**Branch**: `migration`

New Python implementation with better performance and incremental processing.

**Documentation**: [a4d-python/docs/CLAUDE.md](a4d-python/docs/CLAUDE.md)

**Quick Start**:
```bash
cd a4d-python
uv sync
uv run pytest
```

**Migration Guide**: [a4d-python/docs/migration/MIGRATION_GUIDE.md](a4d-python/docs/migration/MIGRATION_GUIDE.md)

---

## Working on This Repository

**If working on R code**: Stay in root, use R commands

**If working on Python migration**:
```bash
cd a4d-python
# See a4d-python/docs/CLAUDE.md for Python-specific guidance
```

## Shared Resources

Both projects use the same reference data:
- `reference_data/synonyms/` - Column name mappings
- `reference_data/data_cleaning.yaml` - Validation rules
- `reference_data/provinces/` - Allowed provinces

**Do not modify these** without testing both R and Python pipelines.
- Always check your implementation against the original R pipeline and check if the logic is the same
- Limit comments to explain why a desigin was made or give important context information for the migration but do not use comments for obvious code otherwise