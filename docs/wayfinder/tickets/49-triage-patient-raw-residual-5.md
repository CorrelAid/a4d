---
id: 49
title: Triage the residual patient raw-stage column mismatches (round 5)
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
4)](46-triage-patient-raw-residual-4.md), closed, which took patient raw-stage
unclassified from **601 to 278** by settling four causes: a number typed into a
date-formatted cell (pipeline fix, 38 rows), R's dropped rich-text space
(classifier, 89), Python's trimming of merged sub-values (classifier, 2), and
`insulin_regimen`'s blank header in `2021_Kantha Bopha` (classifier, 194).

**Updated 2026-08-17, after [ticket
48](48-putrajaya-screening-columns-lost.md) closed.** The residual is now
**229**, measured on baseline run `output/comparison/2026-08-17T222225Z`, which
is the run to triage against. Every count measured before it -- including the
278 below and every per-shape figure in the Question -- is historical.

Ticket 48 removed **49** of the 278, not the ~25 first estimated: its
merged-header fix took `complication_screening_results` 11 -> 0 and
`complication_screening_date` 31 -> 0, and moved 7 `observations` rows from
unclassified onto the existing `r_na_unite_padding` classifier. Three shapes
listed below are therefore already gone -- see the Question's notes.

Rests also on the map's standing scoping rule that the current tracker template
is the golden rule, and on the standing bar that a classifier records
understanding, never a verdict by itself.

## Question

Triage the 229. The shapes below were counted against the *old* 278-row
baseline; three of them are already resolved by ticket 48 and are struck
through in place rather than deleted, so the arithmetic stays checkable.
Re-measure the rest against `output/comparison/2026-08-17T222225Z` before
working them -- do not trust these numbers.

- **R null, Python has a value (~125 rows, ~12 columns)**:
  `last_clinic_visit_date` (40, one file), `fbg_updated_date` (25),
  `blood_pressure_sys_mmhg`/`blood_pressure_dias_mmhg` (13 each), `edu_occ`
  (12), `last_remote_followup_date` (4), `hospitalisation_cause` (3),
  `other_issues` (2), `status` (1). Shape-identical to `r_extraction_gap`, but
  ticket 31's refusal applies: verify per column against the source before
  wiring, or the classifier labels without deciding.
- **A real date typed into a numeric column, or the reverse (51)**:
  ~~`complication_screening_date` (31)~~ -- **resolved by ticket 48**: it was
  exactly the predicted gap, a raw-only date column `get_date_columns()` cannot
  derive, now appended to `PATIENT_RAW_DATE_NORMALIZE_COLS`. 31 -> 0.
  `t1d_diagnosis_age` (16, source defect -- see [ticket
  40](40-source-defect-findings-report.md)), `blood_pressure_mmhg` (3),
  `testing_frequency` (1).
- **`t1d_diagnosis_date` (23, two files)**: R 41837 vs Python 41821 in
  `2017_Yangon` -- two different real dates 16 days apart, so neither side is
  null and neither is obviously right. Unexplained.
- **Booleans (25)**: R `FALSE` vs Python `False` on `clinic_visit` and
  `remote_followup`, one and two files. A representation difference; decide
  normalization vs classifier.
- **R null vs Python empty string (25)**: `insulin_injections` (22),
  `hba1c_updated` (3). Python emitting `""` where the source cell is blank
  looks like a Python cleanliness defect worth fixing rather than classifying.
- **`dm_complications` (15, two files)**: `Kidney \nDamage` on both sides,
  visually identical in the report. Inspect the bytes before assuming a cause.
- **`observations` (8 -> 1)**: mostly **resolved by ticket 48** -- 7 of the 8
  were Putrajaya rows where Python had a screening selection misfiled into
  `observations`; with Python now correctly null they match the existing
  `r_na_unite_padding` classifier. **1 row remains**: R's `... January ,NA`
  against Python's `... January`, where the classifier still does not fire (the
  trailing space before the comma is the likely reason).
- **`complication_screening` (2)**: Python holds two selections where R holds
  one. Ticket 48 established that both pipelines keep only the *first*
  selection of a multi-select block, so re-measure this before assuming it
  still says what it says.
- **`hospitalisation_date` (5)**: Python's raw value is `2958352`, the Excel
  serial for 9999-12-31 -- the date sentinel appearing at the *raw* stage,
  which raw is not supposed to carry.

Split further rather than leaving this open-ended if it does not converge.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.
