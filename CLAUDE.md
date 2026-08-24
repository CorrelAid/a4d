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

## The retired R implementation

The legacy R pipeline used to live at `r-archive/`. It was deleted once the
migration was verified Python-only; nothing in this repo reads it any more.

Recover it from git when you need to check a claim about R's old behaviour:

```bash
git show r-archive-removed^:r-archive/R/script2_process_patient_data.R
git checkout r-archive-removed^ -- r-archive   # whole tree, into the worktree
```

The `r-archive-removed` tag marks the commit that deleted it, so `^` is the
last commit that still contains it. Docstrings citing R files by name are
being removed as part of the documentation overhaul; until that lands, this is
how those citations are checked.

## Shared Resources

- `reference_data/synonyms/` - Column name mappings
- `reference_data/data_cleaning.yaml` - Validation rules
- `reference_data/provinces/` - Allowed provinces

**Do not modify these** without testing the Python pipeline.
- Limit comments to explain why a design was made or give important context;
  do not use comments for obvious code, and do not justify a design by what the
  retired R pipeline did — say what the code does now and why, with real
  examples from the tracker data
