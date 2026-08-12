---
id: 27
title: Triage the residual patient raw-stage column mismatches after date normalization
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
arm](23-triage-patient-arm.md), closed: the patient arm's raw-stage
mismatches were dominated (564,096 of the total, across 70 columns) by the
same representation artifact [ticket
20](20-fix-raw-entry-date-representation.md) found and fixed for product's
raw `product_entry_date` — R's raw extraction stores the unparsed source
text (an Excel serial for date-formatted cells) while Python's raw
extraction already ISO-formats parsed dates. Extending
`normalize_date_column` to every one of the patient cleaned schema's 18
`pl.Date` columns (via the already-existing, schema-derived
`get_date_columns()` helper, wired into `scripts/compare_outputs.py`'s
`STAGES` table for the `Patient (raw)` stage only) confirmed the hypothesis:
raw-stage patient mismatches dropped from 564,096 to 46,788 (91.7%), with
every one of the 18 date columns individually collapsing by 99%+ (e.g. `dob`
79,836 -> 2). No pipeline code changed — this was a comparison-tool fix
only, mirroring ticket 20's precedent exactly.

## Question

Triage the remaining 46,788 raw-stage mismatches across 67 columns (per
`output/comparison/2026-08-12T092205Z/snapshot_patient_data_raw.json`),
the way ticket 18/20/21/22 did for product: look for systematic patterns,
fall back to the real source Excel trackers as the arbiter, and add named
causes to a new `PATIENT_*_CLASSIFIERS` registry in
`src/a4d/migration/compare.py` as patterns are confirmed (none exists yet
for patient). Two leads already surfaced, not yet chased to a cause:

- `complication_screening` (12,566 mismatches, the largest residual column)
  — a spot check on `2021_NPH A4D Tracker` found Python's raw value is a
  comma-joined list of multiple selections (`"Dilated Eye
  Examination,Foot Examination"`) where R's raw value holds only the first
  selection (`"Dilated Eye Examination"`) — looks like a genuine multi-select
  extraction gap on one side, not yet confirmed as systematic or judged
  against the source Excel for which side is right.
- `meter_received_date` (1,761 mismatches) is a raw-only column absent from
  the cleaned schema (so `get_date_columns()` didn't pick it up) but is
  named like a date column — worth checking whether it needs the same
  normalization treatment applied by hand, or has a different cause.

This ticket is large (67 columns) — if it doesn't converge in one session,
split further rather than leaving it open-ended, per the pattern ticket 18
established.
