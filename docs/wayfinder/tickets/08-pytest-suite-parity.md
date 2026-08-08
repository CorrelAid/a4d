---
id: 8
title: Does the pytest suite reach unit/integration/e2e/regression parity between patient and product, excluding any R-comparison/USB-drive-dependent tests?
labels: [wayfinder:grilling]
status: open
blocked_by: [7]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 1
---

## Premise

Rests on [Does product-pipeline's test suite meet the same cell-by-cell rigor
as patient's?](01-product-pipeline-test-rigor.md), closed as superseded: that
session decided R-vs-Python comparison does not belong in pytest (it's
analysis, owned by [Retire the PDF/notebook analysis docs for an automated,
script-based report](02-documentation-strategy.md)), and that pytest's job is
the ordinary category of unit/integration/e2e/regression tests that don't
require the USB drive.

Blocked on [Is the product pipeline (and patient's own claimed completeness)
actually complete and sound, audited against R's product logic and patient's
structure?](07-pipeline-completeness-audit.md) — that ticket produces the
file-by-file test-coverage inventory this ticket needs as its starting fact
base; deciding pytest-suite parity before the inventory exists would mean
re-deriving it from scratch mid-discussion.

## Question

Given the inventory from ticket 7: what, concretely, does pytest-suite parity
between patient and product require — same module-level unit test coverage,
same integration/e2e shape, same regression-test discipline for known fixed
issues? Decide what to do with patient's `test_r_validation.py` specifically
(move out of pytest entirely, e.g. into whatever ticket 2's automated report
becomes, or keep as an opt-in `@pytest.mark.slow` marker but stop treating it
as part of "the test suite" proper) and whether product needs an equivalent
non-R-comparison regression suite before this ticket can close.
