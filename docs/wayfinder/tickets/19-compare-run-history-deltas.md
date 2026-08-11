---
id: 19
title: Persist comparison run history and show run-over-run deltas
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: session-2026-08-11
claimed_at: 2026-08-11
resolution: null
evidence: null
closed_by: null
spawned_by: 17
---

## Premise

Rests on [Fix the product comparison's row-alignment key, then triage every
flagged R/Python difference](17-fix-product-row-alignment-and-triage.md),
closed, and the same session's follow-up conversation about how to work
[Triage every flagged R/Python difference for both arms, and resolve the
189-vs-155-tracker discrepancy](18-triage-comparison-flagged-differences.md):
`build_summary_rows()` (`src/a4d/migration/compare.py`) already computes
`per_column`/`per_cause` mismatch counts per stage on every
`just compare-outputs` run, but nothing persists them — each run only ever
sees the current numbers, with no way to tell whether a fix made in ticket
18 (or any later triage session) actually reduced the count it targeted, or
whether an unrelated pipeline change regressed one that was previously
clean.

Agreed in the same conversation: ticket 18's triage will classify causes
opportunistically (start `unclassified`, add a named classifier the moment
a real pattern is noticed, drop it if it turns out not to earn its keep) —
this run-over-run comparison is what will make a fix's actual effect
visible directly (count before vs. after), rather than needing classifiers
to prove a fix worked.

## Question

Design and implement: after each `compare_outputs.py` run, persist a
compact snapshot of that run's `per_column`/`per_cause` counts (per stage),
and on the next run, load the most recent prior snapshot for that stage and
report a delta (previous vs. current, per column and per cause) alongside
the normal report -- both in the console summary and as an extra sheet in
the stage's Excel workbook. Keep a short history (not just the single most
recent run) so a regression introduced gradually over several runs stays
visible rather than only showing the last hop.

This is tooling to support ticket 18's triage, not triage itself -- keep it
scoped to the persistence/delta mechanism.
