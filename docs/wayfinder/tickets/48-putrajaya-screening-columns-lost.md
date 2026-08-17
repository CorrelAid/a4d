---
id: 48
title: Python drops complication-screening results and dates where a merged header spans the block
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 46
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches (round
4)](46-triage-patient-raw-residual-4.md), closed, which found this while
triaging and split it out rather than chasing it in the same session. It is a
Python data loss, not a triage question, which is why it is its own ticket.

Rests also on [Triage the patient pipeline's raw-stage column-existence
divergence](30-triage-patient-raw-column-divergence.md) (blank-header recovery
from sibling sheets) and [Triage the residual patient raw-stage column
mismatches (round 2)](31-triage-patient-raw-residual-2.md) (merging several
source columns that share one canonical name), because the defect sits in the
same header-handling code both changed and any fix has to leave both working.

## Question

In `2021_Putrajaya Hospital A4D Tracker_DC`, the monthly sheets lay the
complication-screening block out as (verified against the source, `Dec21` header
rows 76/77):

| col | header row 1 | header row 2 |
|-----|--------------|--------------|
| 31 | `Complication Screening \n(Current Month Testing)` | `Select for Drop Down` |
| 32-34 | *(blank -- the row-1 header is merged across the block)* | *(blank)* |
| 35 | *(blank)* | `Results` |
| 36 | *(blank)* | `Date (mmm-yy)` |
| 37 | `Other Patient\nObservations` | |

Python's raw output for `MY_PJ001`/`Dec21` carries:

- `complication_screening` = the col-31 selection (correct)
- `observations` = `Foot Examination (Nerves)` -- a *screening selection*, not
  an observation
- a literal, unmapped column named `Results` holding
  `Urine Albumin:normal Foot:normal  TG:4.2 ...`
- no `complication_screening_results`, no `complication_screening_date`

R gets all three right. Measured on comparison run
`output/comparison/2026-08-17T212151Z`: 11 `complication_screening_results`
cells where R has the recorded results and Python has null, plus
`complication_screening_date` and the mis-filed `observations` rows -- all in
this one file, ~25 cells in total.

To settle:

1. **Which mechanism actually does it** -- the merged row-1 header not being
   propagated across columns 32-36, blank-header recovery filling column 32
   from a sibling sheet that labels it differently, or the duplicate-column
   merge. Instrument rather than infer; three changes have landed in this code
   since it was written.
2. **How many other files it touches.** One file is what the comparison
   surfaces, but the comparison only sees columns R also has. Sweep all 254
   trackers for the same layout (a merged header spanning a block whose
   sub-headers live in row 2 only) before deciding the fix's shape.
3. **Whether the fix belongs in header merging or in the synonym map.**
   Mapping the bare `Results`/`Date (mmm-yy)` sub-headers would fix this file
   and nothing else; propagating a merged header across its span is the
   general rule, and is what R does.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: the
verdict here is already clear (Python loses data the workbook records and R
reads), so this ticket owes a pipeline fix, a regression test, and a
before/after count against the real drive data -- not a classifier.
