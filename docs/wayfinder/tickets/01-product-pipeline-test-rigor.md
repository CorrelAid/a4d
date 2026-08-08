---
id: 1
title: Does product-pipeline's test suite meet the same cell-by-cell rigor as patient's?
labels: [wayfinder:grilling]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
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
