---
id: 5
title: Define and execute the real GCP production verification run
labels: [wayfinder:task]
status: open
blocked_by: [3, 4]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: null
---

## Premise

Depends on [Merge product-pipeline (PR #6) into migration](03-merge-product-pipeline.md)
(need the combined code to run) and [Diagnose and fix why CI is red at migration
HEAD](04-fix-migration-ci.md) (a red CI is not a base to run a production job
from).

This is the destination's core gate: the user wants the merge validated by an
actual GCP run — container deployed, job executed against the production
bucket, output landed in BigQuery — not by tests passing in isolation. Individual
components (product pipeline, state management) have reportedly been tested
against GCP separately already, but never as one combined run.

## Question

Define what "real production run" verification means concretely: which bucket,
what safety/cost bounds, who executes it, and how output is compared against
the R baseline / dashboard numbers (cell-by-cell, per the user's stated
standard). Then execute it and record the result.
