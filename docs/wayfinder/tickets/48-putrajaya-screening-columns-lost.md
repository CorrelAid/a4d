---
id: 48
title: Python drops complication-screening results and dates where a merged header spans the block
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-17e
claimed_at: 2026-08-17T23:30:00+02:00
resolution: decided
evidence: executed
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

## Resolution

**Decision.** A merged upper header now names every column its span covers, but
only where that column has a sub-header of its own to qualify.
`merged_header_spans()` (`src/a4d/extract/patient.py`) reads the sheet's
`<mergeCells>` ranges straight from the XML in the archive openpyxl already has
open, and `merge_headers()` takes them as `merged_spans`. Separately,
`recover_blank_headers()` now abstains for any position inside such a span.
Both were needed: they are two independent mechanisms that happened to damage
the same block.

**Because.** Question 1 asked which mechanism does it, and instrumenting rather
than inferring found *both* of the candidates it listed, doing different harm:

1. *The merged title never propagates.* `merge_headers`' forward-fill carries
   the upper header rightward in `prev_h2` but executes `prev_h2 = None` on any
   column blank in both header rows. In `2021_Putrajaya` `Dec21` the block
   title is merged across columns 31-36 (`AE76:AJ76`, verified in the file) and
   columns 32-34 are blank in both rows, so by column 35 the title is
   forgotten and `Results`/`Date (mmm-yy)` are emitted bare. The synonym map
   **already contains** `Complication Screening (Current Month Testing)
   Results` and its `Date (mmm-yy)` twin -- the fill would have worked; only
   the reset stopped it.
2. *Blank-header recovery then misfiles the leftovers.* Putrajaya's month
   sheets do not share one layout: `Jul21` carries `Patient Observations` at
   the position `Dec21` uses for a screening selection. Ticket 30's
   sibling-donor rule saw exactly one donor and filed `Foot Examination
   (Nerves)` under `observations`. This is why the fix could not be a synonym
   entry (question 3): mapping the bare sub-headers would have left this half
   untouched.

Question 2 asked how many other files it touches, and the answer changed the
fix's shape twice. Sweeping all 254 trackers found **693 sheets across 64
files** with a merged upper header, not one file -- and naive propagation was
actively harmful on two of them:

- The 2022 template merges `Insulin Regimen` across two columns whose second
  holds a **near-duplicate** of the first (`Basal-bolus MDI (AN/HI)` against
  `Basal-bolus (AN/HI)`, 3,659 cells across 10 trackers). Naming both would
  comma-join them into one worse value. R and Python currently **agree** here,
  both taking the first column, so this would have been a self-inflicted
  divergence on data that was never wrong.
- In the 2022 complication-screening block, a column blank in both header rows
  would take the bare block title, which maps to `complication_screening` --
  a column the block's own first column already claims. Measured: **290 sheets
  would gain a second column competing for one standard name.**

Hence the rule adopted: a merged title *qualifies a sub-header*, it never names
a column outright. A column with no sub-header has no name to qualify, and
guessing the block title for it is what caused both hazards. That one rule
drops the collision count to **0** and excludes every Insulin Regimen cell,
with no measured loss -- of the 225 cells that bare-title propagation would
have "recovered", the only mapped ones were the 164 collision cases.

**Rejected.**

- *Stop resetting `prev_h2` on a blank column* (the one-line fix). Makes
  forward-fill unbounded, so a title leaks into a block it does not cover. The
  reset is load-bearing.
- *Add `Results`/`Date (mmm-yy)` to the synonym map.* Fixes this file and
  nothing else, does not touch the `observations` misfiling, and bare
  sub-headers like `Date` recur under several unrelated blocks.
- *Propagate the bare title into columns with no sub-header.* Rejected on
  measurement, above -- 290 standard-name collisions and 3,659 comma-joined
  insulin cells.
- *Load the workbook read-write for openpyxl's own merge metadata.* Gives up
  ticket 10's 6.6x; `merged_header_spans` reads the same information from the
  already-open archive instead, and degrades to today's behaviour if the two
  private attributes it uses ever move.

**What this gives up.** Putrajaya's columns 32-34 hold three further screening
selections (`Foot Examination (Nerves)`, `Lipid profile`, `TSH`) that Python
still drops, because they have no sub-header. R keeps them, but only in
unmapped suffixed columns (`...selectfordropdown1/2/3`), so neither pipeline
carries them into mapped output and the comparison stays quiet about it. Both
pipelines keep only the first selection of a multi-select field. Recorded as
fog rather than fixed here -- it is a shared limitation, not a divergence.

**Evidence: executed.** Every number below was measured, not read.

- Source layout read directly from `2021_Putrajaya Hospital A4D Tracker_DC`
  `Dec21`: header rows 76/77, merged ranges `AE76:AJ76` and `AE77:AH77`.
- Full-run before/after against the real 248-tracker drive data
  (`a4d run patient --force`, 254/254 processed, then `just compare-outputs`),
  baseline run `output/comparison/2026-08-17T212151Z` -> current
  `2026-08-17T222225Z`:
  - `complication_screening_results`: **11 -> 0**
  - `complication_screening_date`: **31 -> 0**
  - `observations`: 8 unclassified -> **1**, the other 7 now matching the
    existing `r_na_unite_padding` classifier because Python's value is
    correctly null
  - patient raw unclassified **278 -> 229**, cleaned **8,148 -> 8,141**
  - no other column moved in either stage; product byte-identical
- Sweeps over all 254 trackers produced the 693/64, 3,659/10 and 290-sheet
  figures above; the collision count under the final rule is 0.
- `2023_Chiang Mai`'s R output carries `complicationscreeningcompletedtsh` --
  R propagates merged headers too, so the renamed columns move Python toward R,
  not away.
- Full suite 742 passed / 1 skipped, `ruff format --check`, `ruff check`,
  `ty check src/` all clean. Four regression tests added
  (`TestMergeHeadersWithMergedSpans`, `TestRecoverBlankHeadersInsideMergedSpan`)
  covering the recovery, both hazards, and the 2021 Kantha Bopha recovery that
  must keep working.

**Tense.** Every claim above describes behaviour after this change, measured;
the 693/64 and 3,659/10 sweep figures describe the source workbooks and are
independent of it.

**One comparison-tool change came with it.** The fix initially made
`complication_screening_date` look *worse* (31 -> 382). It was not: R holds the
Excel serial (`44474`) where Python holds the parsed date (`2021-10-05`) -- the
same date, and the same representation artifact tickets 20/23 already fixed
elsewhere. The column is absent from the cleaned schema (which splits screening
dates per test), so `get_date_columns()` cannot derive it, exactly like
`meter_received_date` in ticket 27. Appended to
`PATIENT_RAW_DATE_NORMALIZE_COLS` with that reason recorded, taking it to 0.
Ticket 49's premise predicted this check.
