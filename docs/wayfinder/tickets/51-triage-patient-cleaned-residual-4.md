---
id: 51
title: Triage the residual patient cleaned-stage mismatches (round 4)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 50
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches (round
6)](50-triage-patient-raw-residual-6.md), closed, which took the patient **raw**
stage to zero unclassified mismatches. Six rounds of raw-stage triage are
finished; the cleaned stage is what remains of the patient arm.

Rests on the three cleaned-stage rounds already closed -- [round
1](29-triage-patient-cleaned-residual.md) (55,670 -> 16,698), [round
2](37-triage-patient-cleaned-residual-2.md) (16,698 -> 8,259) and [the date
family](38-triage-patient-cleaned-date-family.md) (8,259 -> 6,652) -- and on
their standing conclusions, in particular that `r_numeric_error_sentinel` was
exhaustively verified in round 1 and that the date-absence marker list is now
declared once and shared.

Rests also on the map's standing scoping rule that the current tracker template
is the golden rule, and on the standing bar that a classifier records
understanding, never a verdict by itself.

The residual is **7,967 across 129 files and 27 columns**, measured on run
`output/comparison/2026-08-18T214952Z`, which is the run to triage against.
Note that this is *higher* than round 3 left it: later rounds moved the number
in both directions as classifiers were re-scoped and the tracker set was
refreshed to 254 files, so re-measure rather than reasoning from the history.

## Question

Triage the 7,967, largest shapes first. Re-measure against the baseline run
before working any shape -- every round so far has found at least one stated
shape had already moved.

- **`fbg_updated_mmol` (2,936)** is **not** this ticket's work: it is [ticket
  44](44-triage-cleaned-fbg-r-null-residual.md), still open, and the two must
  not be triaged twice. Exclude it and confirm the exclusion by column before
  starting.
- **The date family (3,278 across seven columns)**: `fbg_updated_date` (940),
  `hba1c_updated_date` (904), `t1d_diagnosis_date` (661), `hospitalisation_date`
  (638), `bmi_date` (135), `recruitment_date` (80), `last_clinic_visit_date`
  (60), `lost_date` (18), `last_remote_followup_date` (9). Round 3 worked this
  family and left it at 1,994 sentinel-stamped cells; whether this is the same
  population re-grown by later changes or a different one is the first thing to
  establish.
- **`t1d_diagnosis_age` (558)** and **`bmi` (22)**: both formula-derived in the
  source, so `excel_formula_error` is the raw-stage cause; what survives
  cleaning is a different question.
- **Blood pressure (491)**: `blood_pressure_dias_mmhg` (289),
  `blood_pressure_sys_mmhg` (202).
- **The long tail (~470)**: `height` (114), `fbg_updated_mg` (113), the two
  screening dates (132), `insulin_subtype` (67), `province` (57), and eleven
  columns in single digits. `province` is worth taking early despite its size:
  the map's **Not yet specified** section already suspects Python's
  `sanitize_str` strips accents from province names (`Kratié` -> `krati`), and
  57 cleaned-stage province mismatches is exactly where that would show.

Split further rather than leaving this open-ended if it does not converge --
three rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.
