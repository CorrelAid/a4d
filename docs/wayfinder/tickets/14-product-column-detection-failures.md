---
id: 14
title: Fix product pipeline's "unable to find column product" failures on 4 real trackers
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 10
---

## Premise

Rests on [Profile the combined pipeline's performance against the R baseline
before promoting to dev](10-performance-profiling.md), closed: while running
`process-product` against the full 177-tracker set on the USB drive
(`a4dphase2_upload`) to profile performance, 4 trackers failed outright with
`unable to find column "product"; valid columns: ["index"]` —
`2020_Jayavarman VII Hospital A4D Tracker.xlsx`, `2018_Kantha Bopha Hospital
A4D Tracker.xlsx`, `2019_Kantha Bopha Hospital A4D Tracker.xlsx`,
`2020_Kantha Bopha Hospital A4D Tracker.xlsx`. This is unrelated to ticket
10's performance fix (reproduces identically before and after it) and was not
previously documented anywhere on this map. Not diagnosed further in ticket
10's session, which stayed scoped to performance — the error originates
around `find_product_section` / `extract/product.py`, not investigated
deeper.

Also rests on [Is the product pipeline (and patient's own claimed
completeness) actually complete and sound, audited against R's product logic
and patient's structure?](07-pipeline-completeness-audit.md), closed: that
audit judged R-logic coverage "essentially complete" on product without
surfacing this — these 4 files are a fresh finding from actually running
against the full real dataset, not something the completeness audit's
code-reading caught.

## Question

Why do these 4 trackers fail product extraction with "valid columns:
[\"index\"]" (this looks like `find_product_section` failing to locate the
product/stock section at all, falling back to an empty/index-only frame) —
is it a genuine structural difference in these files' layout (older/different
tracker format for these years), a synonym-mapping gap, or a real regression?
Decide: fix the extraction to handle whatever these files' actual layout is,
or confirm they're legitimately out of scope (e.g. pre-product-tracking
years) and should fail loudly rather than silently, with that decision
recorded either way. Bears on the destination's "every Python/R difference
documented and explicitly decided" bar and on ticket 6's promotion readiness.
