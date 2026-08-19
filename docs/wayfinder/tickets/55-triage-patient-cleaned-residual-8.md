---
id: 55
title: Triage the residual patient cleaned-stage mismatches (round 8)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 54
---

## Premise

Rests on [round 7](54-triage-patient-cleaned-residual-7.md), closed, which took
the cleaned-stage in-scope residual from 1,200 to **770** and settles two things
this ticket must not re-open:

- **R never derives a diagnosis age at all** -- `fix_t1d_diagnosis_age`'s call
  site is commented out (`script2_process_patient_data.R:251`). The whole
  `t1d_diagnosis_age` column is decided; do not re-triage it.
- **The cleaned stage now numeric-normalizes its string-typed columns**
  (`string_numeric_normalize_targets`, `ALL_STRING_COLUMNS`). A float-rounding
  difference on a string-typed measurement column is no longer a mismatch. If
  one reappears, the harness broke -- do not classify it.

Rests on the seven cleaned-stage rounds before it
([1](29-triage-patient-cleaned-residual.md),
[2](37-triage-patient-cleaned-residual-2.md), [the date
family](38-triage-patient-cleaned-date-family.md), [round
4](51-triage-patient-cleaned-residual-4.md), [round
5](52-triage-patient-cleaned-residual-5.md), [round
6](53-triage-patient-cleaned-residual-6.md), [round
7](54-triage-patient-cleaned-residual-7.md)); on [ticket
42](42-fbg-unit-headers-and-implausible-values.md), which set the analytical
bounds on all four FBG columns and owns the medical-limits question; on the
map's rule that the current tracker template is the golden rule; and on the
standing bar that a classifier records understanding, never a verdict by
itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **770** in-scope cells left on run
`output/comparison/2026-08-19T195625Z`, excluding `fbg_updated_mmol` ([ticket
44](44-triage-cleaned-fbg-r-null-residual.md)) and `hospitalisation_date`
([ticket 39](39-recover-dates-embedded-in-free-text.md)). Re-measure before
working any shape.

Round 7 measured every shape below far enough to name a mechanism but did not
decide any of them. **Two look like real Python defects and should be taken
first** -- per the map's bar, where Python is losing or corrupting information
the pipeline gets fixed, not labelled.

- **`height` (114) -- likely a real Python gap.** The source cells hold `6.9`,
  `2.52`, `2.43`, `2.72`, `13.0` (2025/2026 Señor Sto. Niño, 2021-2023 Likas,
  2019 Mahosot). R sentinels every one of them (999999); Python divides by 100
  and emits `0.069`, `0.0252` metres into production output. Whatever the
  source values mean, Python's are not heights. Find R's own height range
  check, decide whether Python needs the equivalent guard, and settle whether
  the source values are a unit the pipeline should recognize or a source defect
  for [ticket 40](40-source-defect-findings-report.md). Check whether these
  rows also feed `bmi` (see below) before deciding either.

- **`fbg_updated_mg` (113) -- two opposite directions, one of them alarming.**
  85 cells where R produces a plain number and Python sentinels: the source
  reads `Lost follow up` (41 cells, R produces **140**), `SMBG 50-HI`,
  `129-HI`, `CBG 57-High`, bare `HI` (R produces **200**). R's `fix_fbg` is
  manufacturing readings from text -- read it and decide whether 200-for-HI is
  a documented clinical convention worth adopting or an invention, and whether
  140-from-"Lost follow up" is anything but garbage. The other direction (~28
  cells) is the reverse and looks like Python winning: the source reads
  `148 mg/dl   (Mar-18)` and Python extracts 148 where R sentinels.

- **`bmi` (22).** R sentinels, Python computes 10-12. Formula-derived in the
  source, so `excel_formula_error` is the raw-stage cause; what survives
  cleaning is a different question. Decide together with `height` -- a BMI
  computed from an implausible height is not a BMI.

- **`insulin_subtype` (67).** R null, Python `Undefined` on every one -- 56 in
  2024 Sarawak, the rest in 2025/2026 Calamba Doctors and 2025 Pahol. The
  source rows carry real brands (`Novorapid` with `Glargine`, `Toujeo`,
  `Ryzodeg`), so Python's derivation runs and its allowed-values validator then
  rejects the result. Decide whether the allowed-value config is missing
  entries -- which would make this a real Python data loss -- or whether the
  subtype genuinely is undefined for these combinations. Note both pipelines
  lose here; R just loses silently.

- **The smaller date columns** -- `hba1c_updated_date` (108),
  `fbg_updated_date` (101), `bmi_date` (88), `recruitment_date` (58),
  `last_clinic_visit_date` (41), `lost_date` (18), `t1d_diagnosis_date` (12),
  `dob` (7), `last_remote_followup_date` (3). Still unmeasured. Round 6
  established that `hospitalisation_date` is *all* clinical notes; whether the
  same holds here is unknown. Split each by direction (Python sentinels / R
  sentinels / both real and differing) before deciding, and hand any
  clinical-note share to ticket 39 rather than triaging it.

- **The long tail (~30):** `hba1c_updated` (8), `fbg_baseline_mg` (6),
  `remote_followup` (2), `testing_frequency` (1), `fbg_baseline_mmol` (1) and
  the columns in single digits -- including the four
  `clinic_visit`/`remote_followup` rows the map's **Not yet specified** section
  has carried since ticket 49, which belong with whatever round works the tail.

Split further rather than leaving this open-ended if it does not converge --
seven rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.
