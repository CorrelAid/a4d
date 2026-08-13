---
id: 37
title: Triage the residual patient cleaned-stage mismatches (round 2)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 29
---

## Premise

Rests on [Triage the residual patient cleaned-stage column
mismatches](29-triage-patient-cleaned-residual.md), closed: that ticket
root-caused the two priority columns its own question named and, along the
way, the whole 999999-sentinel family. Two real Python bugs were found and
fixed (`extract_regimen` lowercasing every value it did not match;
`validate_allowed_values` picking the last of two colliding config
spellings), and three classifiers were added
(`r_insulin_dedup_drop`, `r_join_suffix_collision`,
`r_numeric_error_sentinel`). Cleaned-stage mismatches fell 99,408 ->
95,490 and unclassified rows 55,670 -> 16,698 (-70%), verified against a
fresh 248-tracker pipeline re-run and comparison.

It split the rest off rather than force convergence, per its own
pre-authorization.

## Question

Triage the 16,698 remaining unclassified cleaned-stage mismatches. Re-run
`just compare-outputs` first -- ticket 29's run
(`output/comparison/2026-08-13T221849Z`) is the baseline. Current shape,
largest first:

- **`blood_pressure_updated` (4,504)** -- 4,442 of these are Python-null
  where R holds a value, plus 48 where Python holds the future-date
  sentinel against a Thai Buddhist-Era year in R (2568/2569). The
  Buddhist-Era half is the *inverse* direction of the existing
  `buddhist_era_typo` classifier, which was written for the raw stage
  (R sentinels, Python passes through); at the cleaned stage Python's own
  future-date guard sentinels it and R carries the bad year through. The
  py-null majority is not characterized at all and is the real question.
- **The date-column family: `hospitalisation_date` (2,149),
  `hba1c_updated_date` (1,809), `fbg_updated_date` (1,800),
  `t1d_diagnosis_date` (1,082), `last_clinic_visit_date` (193)** -- each
  mixes four shapes in different proportions: Python-null vs R-value,
  Python-sentinel vs R-date, R-sentinel vs Python-null, and both-real.
  `fbg_updated_date` also shows a 1900-01-03 vs 1900-01-04 pair, which
  looks like the Excel 1900-leap-year serial bug ticket 24 already handled
  once in `STRAY_DATE_CLASSIFIERS` -- worth checking whether that
  classifier's logic applies here.
- **`insulin_type` (1,265)** -- 1,252 are R-null where Python has a real
  value ("Analog Insulin"). `insulin_type` is derived by the same
  `_derive_insulin_fields` step whose sibling `insulin_subtype` is already
  explained by `r_validator_rejects_multivalue`; check first whether this is
  the same cause with a different symptom.
- **`t1d_diagnosis_age`'s remaining 560 and `recruitment_date`'s remaining
  502** -- what is left of each after ticket 28's and ticket 29's causes
  were removed.
- **A tail of ~50 smaller columns**, including `observations` (327) and the
  blood-pressure value pair (`blood_pressure_dias_mmhg` 303,
  `blood_pressure_sys_mmhg` 240), none sampled.

Same method: look for systematic shapes, fall back to the real source Excel
trackers as the arbiter (mount at `/Volumes/USB SanDisk 3.2Gen1 Media/a4d/`),
add named causes to the `PATIENT_*_CLASSIFIERS` registries in
`src/a4d/migration/compare.py` (`scripts/compare_outputs.py`'s
`CLASSIFIERS_BY_COLUMN` wires them to columns) -- or fix a real Python bug
directly, as ticket 29 did twice, when one turns up.

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
