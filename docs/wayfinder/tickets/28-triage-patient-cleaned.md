---
id: 28
title: Triage the patient cleaned-stage column mismatches
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 23
---

## Premise

Rests on [Triage every flagged R/Python difference for the patient
arm](23-triage-patient-arm.md), closed: that ticket's raw-stage date-
representation fix ([ticket 27](27-triage-patient-raw-residual.md) inherits
the residual) is raw-only and confirmed to leave the cleaned stage
completely unaffected (`patient_data_cleaned`'s snapshot is byte-identical
before and after the fix). The cleaned stage's 120,639 mismatches across 61
columns are therefore a separate, untouched body of work — both sides
should already hold parsed dates and cleaned values there, so these are not
expected to be the same representation-artifact class as ticket 27's.

## Question

Triage the patient cleaned-stage mismatches (per
`output/comparison/2026-08-12T092205Z/snapshot_patient_data_cleaned.json`)
the way ticket 18/21 did for product's cleaned stage: look for systematic
patterns, fall back to the real source Excel trackers as the arbiter, and
add named causes to a `PATIENT_*_CLASSIFIERS` registry in
`src/a4d/migration/compare.py` (shared with, or separate from, whatever
[ticket 27](27-triage-patient-raw-residual.md) creates for the raw stage —
that's this ticket's call once both are in view). The largest columns are
`recruitment_date` (28,512), `t1d_diagnosis_age` (25,968),
`insulin_total_units` (16,985), `insulin_subtype` (15,724), and
`fbg_baseline_mg` (9,041) — none yet spot-checked against source. This
ticket is large (61 columns, and patient has more history/format variation
than product per ticket 23's own premise) — if it doesn't converge in one
session, split further rather than leaving it open-ended, per the pattern
ticket 18 established.
