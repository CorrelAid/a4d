---
id: 38
title: Triage the patient cleaned-stage date-column family (round 3)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 37
---

## Premise

Rests on [Triage the residual patient cleaned-stage mismatches (round
2)](37-triage-patient-cleaned-residual-2.md), closed: four real Python bugs
were fixed (the 2022 `Updated 2022` header, the first-space date split, the
broken month-name truncation, and the 2-digit-only month-year branch) and
three causes named (`r_extraction_gap` extended to two more columns,
`r_ifelse_na_propagation`, `buddhist_era_typo` made symmetric). Unclassified
cleaned-stage mismatches fell 16,698 -> 8,259.

It also rests on [Triage the patient cleaned-stage column
mismatches](28-triage-patient-cleaned.md) and [its
residual](29-triage-patient-cleaned-residual.md), which between them
established that R's 999999 sentinel is a correct Python representation
choice and that R's own extraction gaps -- not Python defects -- explain the
largest cleaned-stage columns.

Two of ticket 37's own fixes matter to this ticket's framing: the date parser
now resolves month-year strings to the first of the month deterministically,
and recovers a date followed by a free-text clause via a longest-parseable-
prefix fallback. Several date columns' remaining mismatches are what survived
those fixes, so they are **not** the same population ticket 37 opened with.

Also rests on the tracker set having been refreshed to 254 files with the R
baseline renamed to match (ticket 37's addendum): the current baseline is
`output/comparison/2026-08-14T200342Z`, not any earlier run.

## Question

Triage the 8,259 remaining unclassified cleaned-stage mismatches. Re-run
`just compare-outputs` first. Current shape, largest first, with the value
shapes already measured (`r_sent`/`py_sent` = the 9999-09-09 error date):

- **`hospitalisation_date` (2,111)** -- 1,468 are `r_sent/py_null`, 371
  `r_val/py_sent`, 179 `r_sent/py_val`, 88 `r_val/py_val`. The dominant
  R-sentinel-vs-Python-null shape is the inverse of most causes named so far
  and is not characterized at all. These cells carry free-text clauses
  ("16-Nov-2019 due to DKA"), so ticket 37's prefix fallback is directly
  implicated -- check whether Python's null is a correct "no date recorded"
  or a parse that gives up where R sentinels.
- **`hba1c_updated_date` (1,074) and `fbg_updated_date` (1,032)** -- both
  dominated by `r_val/py_val` (824 and 840): two *real, different* dates on
  each side. That is the hardest shape on the report and the one no cause so
  far explains. `fbg_updated_date` also showed a 1900-01-03 vs 1900-01-04
  pair before ticket 37's fixes -- re-check whether it survives, and whether
  `STRAY_DATE_CLASSIFIERS`'s Excel 1900-leap-year logic applies.
- **`t1d_diagnosis_date` (663)** -- 530 `r_val/py_sent`, i.e. Python's
  future-date guard firing where R carries the date through. Ticket 37
  confirmed one instance of this family is a real source typo, but the
  population was never checked; `python_future_date_sentinel` may simply
  apply, which would be a wiring change rather than an investigation.
- **`t1d_diagnosis_age` (560)** -- what is left after ticket 28's fix and
  ticket 29's `r_numeric_error_sentinel`.
- **A tail of ~50 columns**, none sampled: `observations` (327), the blood
  pressure value pair (`blood_pressure_dias_mmhg` 303,
  `blood_pressure_sys_mmhg` 240), `bmi_date` (190),
  `last_clinic_visit_date` (185), `height` (167), the `fbg_updated` pair
  (163 each).

Carry over one finding ticket 37 deliberately left open: **13 `insulin_type`
rows where both sides hold the same two rows in a different order**, because
`patient_id` + `sheet_name` is duplicated for that patient in that sheet.
Decide whether patient's row-alignment key needs the same treatment product's
did (`add_row_ordinal`, ticket 17) or whether the affected population is
small enough to record and leave -- measure it across all columns first
rather than judging from these 13. [Ticket
31](31-triage-patient-raw-residual-2.md) flagged the same shape on the raw
stage, so whatever is decided here should settle it there too.

Same method: look for systematic shapes, fall back to the real source Excel
trackers as the arbiter (mount at `/Volumes/USB SanDisk 3.2Gen1 Media/a4d/`),
add named causes to the `PATIENT_*_CLASSIFIERS` registries in
`src/a4d/migration/compare.py` (`scripts/compare_outputs.py`'s
`CLASSIFIERS_BY_COLUMN` wires them to columns) -- or fix a real Python bug
directly, as ticket 37 did four times, when one turns up.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: it is not
enough to explain a difference and name a cause. Each one must also carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Noting
"Python has A where R has B" and adding a classifier is not a decision in
favour of A. Where Python turns out to be wrong or to be losing information
the source file carried, fix the pipeline rather than labelling the symptom.
A cause genuinely undecidable on available evidence is recorded as an open
question, not closed with a label; where the evidence shows the source file
itself is corrupt, "the source is wrong, this tracker needs human
inspection" is a legitimate final conclusion.
