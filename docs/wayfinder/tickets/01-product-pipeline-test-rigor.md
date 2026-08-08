---
id: 1
title: Does product-pipeline's test suite meet the same cell-by-cell rigor as patient's?
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-08
claimed_at: 2026-08-08
resolution: superseded
evidence: judgement
closed_by: null
spawned_by: null
---

## Premise

Nothing closed yet — this is one of the map's first tickets.

Facts on record (verified via `git`, not the intern's word): `origin/product-pipeline`
carries 41 test files vs. `migration`'s 26, including `tests/test_clean/test_product.py`,
`tests/test_state/*`, `tests/test_validate/*`, and a source-vs-output reconciliation
module (`src/a4d/validate/source_vs_output_product.py`). PR #6
(`product-pipeline` -> `migration`) is open with its test-plan checkboxes all
unchecked and no CI runs recorded.

## Question

The patient pipeline was verified against 174 trackers, cell-by-cell — shape,
columns, exact values (see Migration Guide Phase 7). Does the product pipeline's
test suite + `source_vs_output_product.py` reconciliation reach the same bar, or
is there a gap (fewer trackers covered, spot-checks instead of exhaustive
comparison, missing edge cases)? What, concretely, is missing if anything?

## Resolution (superseded)

**Decision:** Not answered as framed. The question presupposed patient's
`test_r_validation.py` (174-tracker, hand-written exception dicts, requires
the USB drive) *is* the rigor bar to replicate for product, and that R-vs-Python
sameness is the goal. Both are wrong, established this session with the user:

1. R-parity isn't the goal — Python may correctly diverge from R (R can be
   wrong); the original source Excel trackers are the arbiter when R and
   Python disagree, not R's output alone.
2. Comparing R vs. Python output is *analysis* (a judgment call: why do they
   differ, is it safe to trust), not a *test* (pass/fail assertion) — so it
   doesn't belong in pytest at all. This applies equally to patient's existing
   `test_r_validation.py`, which is itself miscategorized: `@pytest.mark.slow`
   + `@pytest.mark.integration`, hardcoded to the USB drive path, not part of
   a normal `uv run pytest`.
3. Before any test-rigor or output-parity question can be answered, the more
   basic question — is the product pipeline actually complete, and is
   patient's own claimed completeness substantiated — needs answering first.

**Because:** Verified via `git`: `test_r_validation.py` is byte-identical
between `migration` and `origin/product-pipeline` (empty diff) — patient-only,
never extended for product. `source_vs_output_product.py`'s own docstring
states "Group-granularity checks only in v1: per-cell checks would require
reproducing cleaning steps 2.0-2.5 ... which we deliberately avoid" — group
granularity, not cell-by-cell, by explicit design. `PYTHON_IMPROVEMENTS.md`'s
"Schema: 100% match", "production-ready" claims (product-pipeline branch)
cite `Ali_internship/residual_dig.ipynb` (not in the tracked tree) and
`scripts/compare_r_vs_python.py` (patient-only per its own docstring/paths)
— i.e. one-off notebook/script analysis, not a repeatable pytest suite.

**Rejected:**
- Replicating patient's exception-dict pattern for product — rejected: not a
  test if sameness isn't the goal, and the user already found this pattern
  too time-consuming for patient alone.
- A diff-logging pytest suite (log every difference, flag new ones) —
  rejected by the user: still miscategorizes analysis as test, and doesn't
  surface *why* outputs differ, which is what a go-live trust decision needs.
- Answering the ticket as originally scoped — rejected: it assumes facts
  (product pipeline is otherwise complete) that were never established, and
  conflates two different activities (pytest-suite parity vs. R-trust
  analysis) that need separate treatment.

**Evidence:** judgement (the categorical split and the not-1:1-parity
principle are user decisions; the supporting facts above were verified via
`git diff`/`git show`, i.e. read/executed, but the resolution as a whole is
judgement — stamped at the weaker level).

**Tense:** current — all cited facts describe the state of `migration` and
`origin/product-pipeline` as of 2026-08-08, not a future/proposed state.

**Spawned:**
[Is the product pipeline (and patient's own claimed completeness) actually complete and sound, audited against R's product logic and patient's structure?](07-pipeline-completeness-audit.md),
[Does the pytest suite reach unit/integration/e2e/regression parity between patient and product, excluding any R-comparison/USB-drive-dependent tests?](08-pytest-suite-parity.md)
