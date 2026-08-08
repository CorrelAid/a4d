---
id: 3
title: Merge product-pipeline (PR #6) into migration
labels: [wayfinder:task]
status: open
blocked_by: [8, 2]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: null
---

## Premise

Depends on [Does the pytest suite reach unit/integration/e2e/regression
parity between patient and product, excluding any R-comparison/USB-drive-dependent
tests?](08-pytest-suite-parity.md) (itself blocked on [Is the product pipeline
(and patient's own claimed completeness) actually complete and sound, audited
against R's product logic and patient's structure?](07-pipeline-completeness-audit.md))
and [Retire the PDF/notebook analysis docs for an automated, script-based
report](02-documentation-strategy.md) being resolved first — the user's stated
order is product-pipeline readiness before the merge, not merge-then-fix.
(Originally blocked on [Does product-pipeline's test suite meet the same
cell-by-cell rigor as patient's?](01-product-pipeline-test-rigor.md), closed
as superseded and replaced by tickets 7/8 above.)

Facts on record: PR #6 (`product-pipeline` -> `migration`) is `mergeable:
CONFLICTING`. `migration` carries two commits (`2069a4d`, `faa3c28`) not on
`product-pipeline` — error-log-table work touching `tables/logs.py` and
`tables/errors.py` — while `product-pipeline` independently changed
`tables/logs.py` and added `tables/metadata.py`. This is the real source of the
conflict.

## Question

Resolve the merge: reconcile `migration`'s error-log-table commits with
`product-pipeline`'s `logs.py`/`errors.py`/`state/` changes, land PR #6, and
confirm the merged `migration` branch has both arms (patient + product +
state/incremental) working together, not just side by side.
