---
id: 53
title: Triage the residual patient cleaned-stage mismatches (round 6)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: session-2026-08-19c
claimed_at: 2026-08-19T18:00:00+02:00
resolution: null
evidence: null
closed_by: null
spawned_by: 52
---

## Premise

Rests on [round 5](52-triage-patient-cleaned-residual-5.md), closed, which took
the cleaned-stage in-scope residual from 2,538 to **2,278** by settling
`t1d_diagnosis_age` -- and found two real Python bugs doing it, not a labelling
job. Read its resolution before starting; it decides three things this ticket
must not re-open:

- **A bare four-digit year in a date cell is recovered as 1 January of that
  year**, in `parse_date_flexible` *and* in `read_patient_rows` (the second is
  needed only where the cell is date-formatted). The Sarawak cross-year
  evidence settles that Python is right. Do not re-argue it as a source defect.
- **A derived `t1d_diagnosis_age` that goes negative is nulled**, because the
  source's two dates contradict each other. The workbooks are the thing to
  correct -- a [ticket 40](40-source-defect-findings-report.md) finding.
- **`row_has_bare_year_date`** now exists on `CellMismatch`, set across the
  whole row by `compare_cells`. It is the precedent for keying a *derived*
  column's cause on the mechanism rather than on the derived values' shape.

Rests on the five cleaned-stage rounds before it
([1](29-triage-patient-cleaned-residual.md),
[2](37-triage-patient-cleaned-residual-2.md), [the date
family](38-triage-patient-cleaned-date-family.md), [round
4](51-triage-patient-cleaned-residual-4.md), [round
5](52-triage-patient-cleaned-residual-5.md)), on the map's standing scoping
rule that the current tracker template is the golden rule, and on the standing
bar that a classifier records understanding, never a verdict by itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **2,278** in-scope cells left on run
`output/comparison/2026-08-19T174047Z`. Re-measure before working any shape --
every round so far has found at least one stated shape had already moved, and
round 5 moved two of them in the *upward* direction by making Python more
correct.

`fbg_updated_mmol` (2,936) is **not** this ticket's work -- it is [ticket
44](44-triage-cleaned-fbg-r-null-residual.md). Exclude it and confirm the
exclusion by column before starting.

- **`hospitalisation_date` (546)** -- now the largest single shape in scope.
  Round 4 measured this population by joining the sentinelled cells back to
  `patient_data_raw`: Python stamps the date sentinel on a cell it could not
  parse at all, and R guesses -- badly, reading `9-Dce-20` as 2020-09-01. It
  splits into two kinds, and **only the first is takeable here**:
  - *A mangled date token and nothing else* (`9-Dce-20`, `25-Ma4-2025`,
    `4-Okt-2023`, `26/102022`, `19-Jan_2023`). Round 4's verdict, if it holds
    on re-measurement, is that Python is right to refuse and the workbook is
    what needs correcting -- a [ticket 40](40-source-defect-findings-report.md)
    finding.
  - *A date buried in a clinical note* (`DKA - Feb-2020`, `26 Jun (ceton urine
    high)`, `DKA; Jul 2018`). This is [ticket
    39](39-recover-dates-embedded-in-free-text.md)'s open HITL question. Do not
    decide it here; measure it and leave it.
  The same split governs the smaller date columns: `hba1c_updated_date` (108),
  `fbg_updated_date` (103), `bmi_date` (94), `recruitment_date` (72),
  `last_clinic_visit_date` (41), `lost_date` (18).
- **Blood pressure (491)**: `blood_pressure_dias_mmhg` (289),
  `blood_pressure_sys_mmhg` (202). These columns already carry
  `r_extraction_gap` for the 2026 template's Annual sheet, so the residual is
  something else.
- **`t1d_diagnosis_age` (298 left)** -- the share round 5 did *not* explain.
  590 of 597 `age` mismatches proved to sit on a bare-year row, but only 239 of
  537 diagnosis-age ones did, so the remainder is a different mechanism.
  Round 5 found two of its shapes without deciding them: R stamps the 999999
  sentinel where the source records an age with a unit (`11yr`, `4mth`, 2017
  Mandalay) that Python parses, and R carries a raw Excel serial (20668) into
  the age column in 2023 Chiang Mai where Python has null.
- **`height` (114)**, **`fbg_updated_mg` (113)**, **`bmi` (22)** -- untouched
  by rounds 4 and 5. `bmi` is formula-derived in the source, so
  `excel_formula_error` is the raw-stage cause; what survives cleaning is a
  different question.
- **The long tail (~300)**:
  `complication_screening_lipid_profile_cholesterol_value` (72),
  `insulin_subtype` (67), `complication_screening_kidney_test_value` (60), and
  the columns in single digits -- including the four
  `clinic_visit`/`remote_followup` rows the map's **Not yet specified** section
  has been carrying since ticket 49, which belong with whatever round works the
  tail.

Split further rather than leaving this open-ended if it does not converge --
five rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.
