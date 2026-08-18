---
id: 52
title: Triage the residual patient cleaned-stage mismatches (round 5)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 51
---

## Premise

Rests on [round 4](51-triage-patient-cleaned-residual-4.md), closed, which took
the cleaned-stage in-scope residual from 5,031 to **2,538** by landing three
causes: `r_ymd_first_misparse` (1,714), `python_rejects_beyond_tracker_year`
(722) and `r_unicode_sanitizer_rejects_accent` (57). Read its resolution before
starting -- it decides three things this ticket must not re-open:

- **R's date parsing is year-first and wrong**, so any further date divergence
  should be checked against `r_ymd_first_misparse` before being called new.
- **Python's beyond-tracker-year guard is a deliberate divergence from R**, not
  a parity gap, and `_validate_dates`'s docstring now says so.
- **Python's ASCII-folding `sanitize_str` is safe on allowed-value columns**,
  because `validate_allowed_values` raises on any two allowed values that
  sanitize alike. Do not re-argue the accent question.

Rests on the four cleaned-stage rounds before it ([1](29-triage-patient-cleaned-residual.md),
[2](37-triage-patient-cleaned-residual-2.md), [the date
family](38-triage-patient-cleaned-date-family.md), [round
4](51-triage-patient-cleaned-residual-4.md)) and on the map's standing scoping
rule that the current tracker template is the golden rule, and on the standing
bar that a classifier records understanding, never a verdict by itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **2,538** in-scope cells left on run
`output/comparison/2026-08-18T222716Z`. Re-measure before working any shape;
every round so far has found at least one stated shape had already moved.

`fbg_updated_mmol` (2,936) is **not** this ticket's work -- it is [ticket
44](44-triage-cleaned-fbg-r-null-residual.md). Exclude it and confirm the
exclusion by column before starting.

- **`t1d_diagnosis_age` (558)** and **`height` (114)**, **`bmi` (22)** --
  untouched by round 4. `t1d_diagnosis_age` is formula-derived in the source,
  so `excel_formula_error` is the raw-stage cause; what survives cleaning is a
  different question. Largest single shape in scope: take it first.
- **The parse-failure date cells (~533 measured in round 4, spread across
  `hospitalisation_date` 546, `hba1c_updated_date` 108, `fbg_updated_date` 103,
  `bmi_date` 94, `recruitment_date` 72, `last_clinic_visit_date` 41, and a
  small tail).** Round 4 measured this population by joining the sentinelled
  cells back to `patient_data_raw`: Python stamps the date sentinel on a cell
  it could not parse at all, and R guesses -- badly, reading `9-Dce-20` as
  2020-09-01. It splits into two kinds, and **only the first is takeable here**:
  - *A mangled date token and nothing else* (`9-Dce-20` 81 cells,
    `25-Ma4-2025` 18, `4-Okt-2023` 3, `26/102022` 5, `19-Jan_2023` 5). Round 4's
    verdict, if it holds on re-measurement, is that Python is right to refuse
    and the workbook is what needs correcting -- a [ticket
    40](40-source-defect-findings-report.md) finding.
  - *A date buried in a clinical note* (`DKA - Feb-2020` 20,
    `26 Jun (ceton urine high)` 30, `DKA; Jul 2018` 12, `admitted to Yangon
    General Hosp...`). This is [ticket
    39](39-recover-dates-embedded-in-free-text.md)'s open HITL question. Do not
    decide it here; measure it and leave it.
- **Blood pressure (491)**: `blood_pressure_dias_mmhg` (289),
  `blood_pressure_sys_mmhg` (202). Note these columns already carry
  `r_extraction_gap` for the 2026 template's Annual sheet, so the residual is
  something else.
- **The long tail (~370)**: `fbg_updated_mg` (113),
  `complication_screening_lipid_profile_cholesterol_value` (72),
  `insulin_subtype` (67), `complication_screening_kidney_test_value` (60),
  `lost_date` (18), and nine columns in single digits.

Split further rather than leaving this open-ended if it does not converge --
four rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.
