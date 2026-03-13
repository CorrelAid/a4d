# CLAUDE.md

## Python Pipeline

**Location**: Repo root
**Branch**: `migration`

Python implementation of the A4D medical tracker data processing pipeline.

**Key Directories**:
- `src/` - Python package source
- `tests/` - Test suite
- `docs/` - Documentation (see [docs/CLAUDE.md](docs/CLAUDE.md) for detailed guidance)
- `scripts/` - Utility scripts
- `reference_data/` - Shared YAML configs (synonyms, validation rules, provinces)

**Quick Start**:
```bash
uv sync
uv run pytest
```

**Migration Guide**: [docs/migration/MIGRATION_GUIDE.md](docs/migration/MIGRATION_GUIDE.md)

## R Archive

**Location**: `r-archive/`

Legacy R implementation, preserved for reference. Do not modify.

## Shared Resources

- `reference_data/synonyms/` - Column name mappings
- `reference_data/data_cleaning.yaml` - Validation rules
- `reference_data/provinces/` - Allowed provinces

**Do not modify these** without testing the Python pipeline.
- Always check your implementation against the original R pipeline and verify the logic is the same
- Limit comments to explain why a design was made or give important context for the migration; do not use comments for obvious code
