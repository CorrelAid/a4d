---
id: 6
title: Promote migration into dev via PR #2
labels: [wayfinder:task]
status: open
blocked_by: [1, 2, 3, 4, 5]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: null
---

## Premise

Depends on every other ticket on this map: [Does product-pipeline's test suite
meet the same cell-by-cell rigor as patient's?](01-product-pipeline-test-rigor.md),
[Retire the PDF/notebook analysis docs for an automated, script-based
report](02-documentation-strategy.md), [Merge product-pipeline (PR #6) into
migration](03-merge-product-pipeline.md), [Diagnose and fix why CI is red at
migration HEAD](04-fix-migration-ci.md), and [Define and execute the real GCP
production verification run](05-production-verification-run.md).

PR #2 (`migration` -> `dev`) already exists and is `mergeable: MERGEABLE`; it is
gated only on the work above landing first.

## Question

With the merge done, CI green, and a real production run validated, close out
PR #2 and merge `migration` into `dev`. This is the destination.
