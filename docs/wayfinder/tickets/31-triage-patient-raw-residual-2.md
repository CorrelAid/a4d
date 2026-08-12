---
id: 31
title: Triage the residual patient raw-stage column mismatches (round 2)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 27
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches after date
normalization](27-triage-patient-raw-residual.md), closed: extending
`normalize_numeric_column` to patient's raw numeric columns (derived via
`get_numeric_columns()`) and `normalize_date_column` to the raw-only
`meter_received_date`, plus two new classifiers (`r_formula_error` for
Excel formula-error strings R's raw extraction carries through where
Python's correctly has no cached value; `buddhist_era_typo` for a
clinician-entered Thai Buddhist-Era year in a Gregorian date cell,
confirmed harmless by the cleaned stage's existing future-date guard)
together cut raw-stage patient mismatches from 46,788 to 18,813 (59.8%).
`complication_screening` (12,566, the single largest residual column, 84%
of what remains) was explicitly left unchased -- ticket 27 judged it a
different kind of investigation (content/extraction-logic, not a
representation gap) rather than sprawl past its own two original leads.

## Question

Triage the remaining 18,813 raw-stage mismatches across roughly 50 columns
(per `output/comparison/2026-08-12T200529Z/snapshot_patient_data_raw.json`),
continuing the pattern ticket 20/21/22/24/27 established: look for
systematic shapes, fall back to the real source Excel trackers as the
arbiter, add named causes to `PATIENT_*_CLASSIFIERS` registries in
`src/a4d/migration/compare.py` as patterns are confirmed. Current shape,
largest first:

- `complication_screening` (12,566) -- ticket 27's own lead, not yet
  chased to a cause: a spot check on `2021_NPH A4D Tracker` found Python's
  raw value is a comma-joined list of multiple selections
  (`"Dilated Eye Examination,Foot Examination"`) where R's raw value holds
  only the first selection (`"Dilated Eye Examination"`) -- looks like a
  genuine multi-select extraction gap on one side, not yet confirmed as
  systematic across files or judged against the source Excel for which
  side is right.
- `observations` (358) -- same comma-joined-list shape observed in ticket
  24/27's exploratory samples (e.g. `"Transfer to PKH,NA"` vs
  `"Transfer to PKH"`); worth checking whether it's the same root cause as
  `complication_screening` or a separate one.
- `latest_complication_screenning` (308), `fbg_baseline_mg.static` (192),
  `fbg_baseline_mmol.static` (110) -- not yet looked at.
- A long tail of ~46 columns each under 100 mismatches, several showing a
  swapped-adjacent-row shape in early sampling (`status`, `insulin_regimen`,
  `age` each showed r/py values that looked like two rows' values traded
  places) -- worth checking whether this is a genuine row-alignment issue
  (patient's key is `patient_id` + `sheet_name`, confirmed sound by ticket
  15, but duplicate keys existed in 5/172 files at that time) rather than a
  per-column content bug.
- `hba1c_updated` (88) and `fbg_updated_mg` (44) show a same-value
  spacing-only variant in early sampling (`"8.8(20.9.16)"` vs
  `"8.8 (20.9.16)"`) -- may be another readxl-vs-openpyxl whitespace
  convention, similar in spirit to ticket 22's `normalize_whitespace_column`
  but on a substring rather than the whole value.
- The remaining date columns' non-Buddhist-Era residual
  (`last_clinic_visit_date` 89, `fbg_updated_date` 75, `hba1c_updated_date`
  39, `bmi_date` 43, etc.) -- not yet characterized.

This ticket is large -- if it doesn't converge in one session, split further
rather than leaving it open-ended, per the pattern ticket 18/27 established.


## Standing bar (added 2026-08-12g, applies to this ticket)

Per the map's **triage means deciding, not labelling** preference: it is not
enough to explain a difference and name a cause. Each one must also carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Noting
"Python has A where R has B" and adding a classifier is not a decision in
favour of A. Where Python turns out to be wrong or to be losing information
the source file carried, fix the pipeline rather than labelling the symptom
— see [ticket 27](27-triage-patient-raw-residual.md), where exactly that
turned a labelling job into a real extraction fix. A cause genuinely
undecidable on available evidence is recorded as an open question, not
closed with a label.
