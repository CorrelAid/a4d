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

The **278 that remain** are measured on baseline run
`output/comparison/2026-08-17T212151Z`, which is the run to triage against.
Every count on the map measured before it is historical.

The Putrajaya screening-column loss found in the same session is **not** this
ticket's -- it is [ticket 48](48-putrajaya-screening-columns-lost.md), and its
~25 cells are part of the 278 counted here. Subtract them rather than
re-diagnosing them.

Rests also on the map's standing scoping rule that the current tracker template
is the golden rule, and on the standing bar that a classifier records
understanding, never a verdict by itself.

## Question

Triage the 278. The shapes, by count, against the baseline run above:

- **R null, Python has a value (~125 rows, ~12 columns)**:
  `last_clinic_visit_date` (40, one file), `fbg_updated_date` (25),
  `blood_pressure_sys_mmhg`/`blood_pressure_dias_mmhg` (13 each), `edu_occ`
  (12), `last_remote_followup_date` (4), `hospitalisation_cause` (3),
  `other_issues` (2), `status` (1). Shape-identical to `r_extraction_gap`, but
  ticket 31's refusal applies: verify per column against the source before
  wiring, or the classifier labels without deciding.
- **A real date typed into a numeric column, or the reverse (51)**:
  `complication_screening_date` (31, R serial vs Python parsed date -- check
  first whether this is simply a date column the raw normalize list cannot
  name, the same gap ticket 27 found for `meter_received_date`),
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
- **`observations` (8)**: R's `... January ,NA` against Python's `... January`
  -- `r_na_unite_padding` did not fire; find out why (the trailing space before
  the comma is the likely reason).
- **`complication_screening` (2)**: Python holds two selections where R holds
  one.
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
