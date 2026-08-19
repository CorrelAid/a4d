---
id: 54
title: Triage the residual patient cleaned-stage mismatches (round 7)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 53
---

## Premise

Rests on [round 6](53-triage-patient-cleaned-residual-6.md), closed, which took
the cleaned-stage in-scope residual from 2,278 to **1,689** by fixing two Python
defects rather than labelling them. Read its resolution before starting; it
settles three things this ticket must not re-open:

- **`parse_date_flexible` no longer lets dateutil invent a component from
  today.** An absent day resolves to the 1st; an absent month or year makes the
  cell unparseable. Do not re-add a month-year spelling to the pattern -- the
  probe-the-defaults mechanism closes the class.
- **`split_bp_in_sys_and_dias` trims each fragment**, so a source written
  `70 / 40` keeps its reading. Blood pressure has left the residual; do not
  expect it back.
- **`hospitalisation_date` (489) is entirely [ticket
  39](39-recover-dates-embedded-in-free-text.md)'s**, in all three of its
  directions, including the newly measured one where *both* pipelines find a
  date and disagree about which of several admissions the cell means. It is
  deliberately left unclassified. Do not triage it here and do not label it.

Rests on the six cleaned-stage rounds before it
([1](29-triage-patient-cleaned-residual.md),
[2](37-triage-patient-cleaned-residual-2.md), [the date
family](38-triage-patient-cleaned-date-family.md), [round
4](51-triage-patient-cleaned-residual-4.md), [round
5](52-triage-patient-cleaned-residual-5.md), [round
6](53-triage-patient-cleaned-residual-6.md)), on the map's standing scoping rule
that the current tracker template is the golden rule, and on the standing bar
that a classifier records understanding, never a verdict by itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **1,689** in-scope cells left on run
`output/comparison/2026-08-19T185253Z`, excluding `fbg_updated_mmol` ([ticket
44](44-triage-cleaned-fbg-r-null-residual.md)) and `hospitalisation_date`
(ticket 39). Re-measure before working any shape -- every round so far has found
at least one stated shape had already moved.

The method that found both of round 6's defects, and round 5's: **join the
flagged cells back to Python's own raw stage and group by the *source* value**,
not by the shape of the two outputs. A population that is homogeneous at the
source is a mechanism; one that is only homogeneous in the report may be a
coincidence.

- **`t1d_diagnosis_age` (298)** -- now the largest takeable shape, measured by
  round 6 but deliberately not decided. Three sub-shapes, all of which look
  decidable:
  - *R null, Python derives an age* (dominant; 2024/2025/2026 Sarawak, 2021
    Children's Hospital 2). Both `dob` and `t1d_diagnosis_date` are present on
    Python's side and R failed to parse one of them -- for Sarawak these are the
    bare-year dates [round 5](52-triage-patient-cleaned-residual-5.md)
    recovered, so this is likely a downstream face of `python_reads_bare_year`
    that `python_age_from_bare_year` does not catch, because extraction now
    resolves the bare year before the classifier can see it.
  - *R 999999, Python 0*: the source records an age in words -- `4 months`,
    `4mth`, `At birth` (2017/2018 Mandalay, 2017/2018 Yangon) -- which R cannot
    parse, while Python derives 0 from the two dates.
  - *R 20668, Python null*: 2023 Chiang Mai has a **date** (`1956-08-01`) typed
    into the age column; R carries the Excel serial into the age, Python nulls
    it. A [ticket 40](40-source-defect-findings-report.md) source-defect
    finding if it holds.
- **The smaller date columns** -- `hba1c_updated_date` (108),
  `fbg_updated_date` (101), `bmi_date` (88), `recruitment_date` (58),
  `last_clinic_visit_date` (41), `lost_date` (18), `t1d_diagnosis_date` (12),
  `dob` (7), `last_remote_followup_date` (3). Round 6 established that
  `hospitalisation_date` is *all* clinical notes; whether the same holds for
  these is unmeasured. Split each by direction (Python sentinels / R sentinels /
  both real and differing) before deciding, and hand any clinical-note share to
  ticket 39 rather than triaging it.
- **`height` (114)**, **`fbg_updated_mg` (113)**, **`bmi` (22)** -- untouched by
  rounds 4, 5 and 6. `bmi` is formula-derived in the source, so
  `excel_formula_error` is the raw-stage cause; what survives cleaning is a
  different question.
- **The long tail (~200)**:
  `complication_screening_lipid_profile_cholesterol_value` (72),
  `insulin_subtype` (67), `complication_screening_kidney_test_value` (60),
  `hba1c_updated` (8), `fbg_baseline_mg` (6), and the columns in single digits
  -- including the four `clinic_visit`/`remote_followup` rows the map's **Not
  yet specified** section has been carrying since ticket 49, which belong with
  whatever round works the tail.

Split further rather than leaving this open-ended if it does not converge -- six
rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.
