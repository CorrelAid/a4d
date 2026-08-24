# Archive — the R-to-Python migration

**These documents are frozen. Nothing here is current guidance.**

They are the record of a finished piece of work: the migration of the A4D
medical tracker pipeline from R to Python. Every one of them is written in
terms of the R pipeline, because comparing against R is what the work
consisted of. The R pipeline itself was deleted from this repository on
2026-08-24.

Frozen at the tag **`migration-archive-frozen`**. Resolve it with
`git rev-parse migration-archive-frozen`; that commit is the last state in
which these documents were checked against the code. They are not maintained
after it, and a fact stated here should be assumed stale unless the code
agrees.

## Where to look instead

| For | Read |
|---|---|
| What the pipeline does and how to run it | [`README.md`](../../README.md), [`SETUP.md`](../../SETUP.md) |
| Module-by-module map, CLI, output layout | [`docs/CLAUDE.md`](../CLAUDE.md) |
| Why a particular cleaning rule exists | the docstring on the rule itself |
| The migration's decision history | [`docs/wayfinder/`](../wayfinder/map.md) |
| The old R source | `git show r-archive-removed^:r-archive/R/<file>` |

## What is here

- **`MR_DESCRIPTION.md`** — the description of PR #2 (`migration` -> `dev`).
  The fullest single account of what changed and what was verified. Live until
  that PR merges; frozen thereafter.
- **`MIGRATION_GUIDE.md`** — the phase-by-phase plan the migration followed,
  plus the R-to-Python step mapping.
- **`PYTHON_IMPROVEMENTS.md`** — cases where Python was judged more correct
  than R. Superseded as a *catalogue* by the cause registry in
  `src/a4d/migration/compare.py` and by the wayfinder map's decisions, both of
  which are evidence-backed where this document is not.
- **`PRODUCT_DATA_PIPELINE_FEATURE.md`** — the original proposal for the
  product arm, written before it was built. Already marked obsolete in its own
  header.
- **`Product pipeline parity presentation.pdf`** — the parity presentation the
  comparison script was built to supersede.

## Why they were kept rather than deleted

The migration's conclusions rest on cell-by-cell evidence gathered over 56
wayfinder tickets. Those conclusions are now expressed where they belong — in
the code's own docstrings, in the wayfinder map, and in the comparison tool's
cause registry. These documents are the working papers behind them. They cost
nothing to keep and they are the only place some of the intermediate reasoning
survives.
