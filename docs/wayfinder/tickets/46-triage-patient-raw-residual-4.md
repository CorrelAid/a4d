---
id: 46
title: Triage the residual patient raw-stage column mismatches (round 4)
labels: [wayfinder:task]
status: open
blocked_by: [45]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 43
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches (round
3)](43-triage-patient-raw-residual-3.md), closed, which took patient
raw-stage unclassified from 1,879 to **1,409** by settling two causes: a
float-to-string rounding artifact reaching four columns the normalize list
could not name (434 rows, comparison-tool fix), and 24 invented rows in
`2024_Vietnam National Children`'s `Jul24` that Python was reading from a
bare list of patient IDs below the data block (pipeline fix).

Blocked on [Give the patient comparison an ordinal row key](45-patient-row-alignment-duplicate-keys.md)
deliberately: 808 of the 1,409 are join fan-out in three duplicate-key files,
so triaging the tail before that lands would mean characterizing noise. What
this ticket inherits is the **~600 rows outside those three files**.

Also rests on the map's standing scoping rule that the current tracker
template is the golden rule, and on ticket 43's own warning that early
sampling of these columns predates three extraction changes (ticket 30's
blank-header recovery, ticket 31's duplicate-source-column merge, ticket 43's
phantom-row fix) -- so re-measure rather than trusting any characterization
written before baseline run `output/comparison/2026-08-17T192144Z`.

## Question

Triage what remains once ticket 45 has realigned the duplicate-key files.
Shapes ticket 43 measured but did not close, all against the pre-45 baseline:

- **`hba1c_updated` / `fbg_updated_mg` interior space, 86 rows -- Python
  already verified right, cause not yet named.** All 86 are in `2017_Yangon
  Children's Hospital`, R holding `8.8(20.9.16)` where Python holds `8.8
  (20.9.16)`. The source cell (`Feb17`, row 62, column 12) was read directly
  and **contains the space**, so Python reproduces the workbook exactly and R
  drops it. Ticket 43 searched R's raw path for the mechanism and did not
  find it (`sanitize_str` touches only column names and validator lookups;
  the multiline-header merge touches only headers; the wide-format splitter
  is product-side). Either locate it or wire a classifier that says what was
  verified -- that Python matches source -- without claiming a mechanism.
- **`insulin_regimen` (234).** Ticket 43 did not reach this. 194 rows are
  ticket 30's source-verified blank-header recovery in `2021_Kantha Bopha`;
  the other ~40 share the shape but were never verified, which is exactly why
  ticket 31 refused to wire the column to `r_extraction_gap` wholesale.
  Verify the unverified ones against source, or split the classifier so it
  fires only where the evidence reaches.
- **`observations` (55), `observations_category` (42), `status` (43),
  `last_clinic_visit_date` (82), `fbg_updated_date` (74), `hba1c_updated`
  (87)** and ~40 more columns under 45 rows each. Expect a large share of the
  date-column entries to be the duplicate-key fan-out and to disappear with
  ticket 45 -- re-measure first, then triage what survives.
- **Cheap representation shapes worth one decision each**: R `FALSE` vs
  Python `False` (20 rows, `clinic_visit` and `remote_followup`); R `null` vs
  Python `""` (25 rows, mostly `insulin_injections`); a trailing space inside
  a merged sub-value (`"Normal ,Insulin"` vs `"Normal,Insulin"`), which
  ticket 31's merge strips and R's `unite` does not -- decide whether to
  extend `normalize_whitespace_column` to interior whitespace or classify.

Split further rather than leaving this open-ended if it does not converge.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining
a difference and naming a cause is not enough -- each needs an explicit
verdict on whether Python is right, with the evidence. Where Python is losing
information the source carried, fix the pipeline. Where the source workbook
itself is wrong, that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on
the available evidence is recorded as an open question, not closed with a
label.
