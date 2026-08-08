---
id: 3
title: Merge product-pipeline (PR #6) into migration
labels: [wayfinder:task]
status: open
blocked_by: [8]
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
being resolved first — the user's stated order is product-pipeline readiness
before the merge, not merge-then-fix. (Originally blocked on [Does
product-pipeline's test suite meet the same cell-by-cell rigor as
patient's?](01-product-pipeline-test-rigor.md), closed as superseded and
replaced by tickets 7/8 above.)

**No longer blocked on** [Retire the PDF/notebook analysis docs for an
automated, script-based report](02-documentation-strategy.md) — the user
corrected this sequencing: the R-vs-Python comparison script only makes
sense to build once patient and product live on one branch, not before, so
it belongs *after* this merge rather than gating it. Ticket 2 is now blocked
by this ticket instead of the reverse. The merge's actual readiness bar is
tests green (ticket 8) plus ordinary pre-merge hygiene the user named
explicitly: code style, a review pass on the implementation itself (are all
of R's steps actually migrated, not just tested), and doc alignment with the
patient pipeline's conventions — not proof of R/Python output parity, which
this ticket's own review process (green tests + a clean implementation
review) is judged sufficient grounds to trust without first.

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
state/incremental) working together, not just side by side. Before landing
it, also confirm the pre-merge hygiene bar the user set: ticket 8's tests
green, a code-style pass, an implementation review confirming all of R's
product-side steps are actually migrated (not just individually tested), and
doc alignment with the patient pipeline's conventions.
