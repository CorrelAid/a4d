---
id: 56
title: Triage the residual patient cleaned-stage mismatches (round 9)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 55
---

## Premise

Rests on [round 8](55-triage-patient-cleaned-residual-8.md), closed, which took
the in-scope cleaned residual from 770 to **448** and settles four things this
ticket must not re-open:

- **`height`, `bmi` and `fbg_updated_mg` are decided.** Python's cm-to-m
  threshold now matches R's 50, BMI is derived after the height cut, and R's
  `fix_fbg` is confirmed to manufacture readings from text. Do not re-triage
  them; if one reappears, a fix regressed.
- **`parse_date_flexible` now rejects any year below 1900.** A date in
  antiquity is no longer reachable from a source year typed short. The date
  columns below are what survives that fix, not what preceded it.
- **`insulin_subtype`'s drug-name rows are recovered** and only the 11
  `Undefined`-against-null cells remain.
- **An unticked insulin row keeping `Undefined` is deliberate**, not an
  oversight: R publishes the same on 17,418 rows where the two pipelines agree.
  It is fog on the map, not this ticket's to change.

Rests on the eight cleaned-stage rounds before it, on [ticket
42](42-fbg-unit-headers-and-implausible-values.md) for the FBG analytical
bounds, on the map's rule that the current tracker template is the golden rule,
and on the standing bar that a classifier records understanding, never a
verdict by itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **448** in-scope cells left on run
`output/comparison/2026-08-19T205332Z`, excluding `fbg_updated_mmol` ([ticket
44](44-triage-cleaned-fbg-r-null-residual.md)) and `hospitalisation_date`
([ticket 39](39-recover-dates-embedded-in-free-text.md)). Re-measure before
working any shape.

- **The date family (412), which is now almost the whole residual.**
  `hba1c_updated_date` (103), `fbg_updated_date` (91), `bmi_date` (87),
  `recruitment_date` (58), `last_clinic_visit_date` (40), `lost_date` (18),
  `t1d_diagnosis_date` (12), `dob` (7), `last_remote_followup_date` (3). Round
  8 measured the direction split rather than the causes, and killed the obvious
  framings: only **2** of 414 are a day/month swap and **none** is a year-only
  difference, so this is not a systematic parse-order divergence. It is
  concentrated by tracker instead -- 2021 Mahosot DC and 2020 Mahosot DC
  together account for roughly 150, and within them R and Python each sentinel
  where the other holds a real date, on the same rows across all three of
  `hba1c_updated_date`, `fbg_updated_date` and `bmi_date`. That the three
  columns move together points at
  `_extract_date_from_measurement` / R's `extract_date_from_measurement` (the
  legacy path that lifts a date out of the measurement cell's parentheses)
  rather than at nine separate causes. Start there, per tracker, and hand any
  clinical-note share to [ticket 39](39-recover-dates-embedded-in-free-text.md)
  rather than triaging it.
- **`insulin_subtype` (11).** R holds null, Python `Undefined`, in 2025/2026
  Calamba Doctors and 2025 Pahol. These rows tick nothing (`-` in all five
  columns) -- but R publishes `Undefined` for the 17,418 rows whose columns are
  all *null*, so R distinguishes the two cases and Python does not. Find what
  R's derivation does with an all-`-` row and decide whether Python should
  follow.
- **The long tail (~25):** `hba1c_updated` (8), `dob` (7), `fbg_baseline_mg`
  (6), `remote_followup` (2), `testing_frequency` (1), `fbg_baseline_mmol` (1)
  -- including the four `clinic_visit`/`remote_followup` rows the map's **Not
  yet specified** section has carried since ticket 49, which belong with
  whatever round works the tail. `fbg_baseline_mg` is worth a direct look
  first: round 8 wired the FBG text classifiers to that column too, so what is
  left there is a different mechanism.

Split further rather than leaving this open-ended if it does not converge --
eight rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is
wrong, that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.
