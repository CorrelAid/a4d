---
id: 23
title: Triage every flagged R/Python difference for the patient arm (raw and cleaned)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-12b
claimed_at: 2026-08-12T09:20:00+00:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 18
---

## Premise

Rests on [Build and run the R/Python output comparison script, then triage
every flagged difference](15-build-and-run-comparison-script.md), closed:
the patient arm's row-alignment key (`patient_id` + `sheet_name`) was
confirmed sound (duplicate keys in only 5/172 files) and a full comparison
ran successfully, but the flagged differences were never triaged — all of
this map's triage attention (tickets 15, 17, 18) went to the product arm,
whose row-alignment key needed fixing first. [Triage every flagged R/Python
difference for both arms, and resolve the 189-vs-155-tracker
discrepancy](18-triage-comparison-flagged-differences.md), also closed,
reconfirmed the patient arm was still untouched and split it out explicitly
rather than starting it in an already-large session.

Also rests on ticket 18's 189-vs-155-tracker finding for the product arm
specifically — check whether an analogous tracker-count gap exists on the
patient side (R: 172 files, Python: 174 files per ticket 18's session) before
assuming patient's per-column counts are directly comparable to any prior
baseline; the gap here is much smaller (2 files) than product's (34), so it
may not need the same treatment, but confirm rather than assume.

**Updated same day, per ticket 18's addendum:** R and Python were both
re-run against the current 248-tracker production set (up from 177) —
`output_r/` now holds fresh R output (243 patient-cleaned files, 81,859
rows; old baseline preserved at `output_r_155_frozen_backup_2025-11-14`)
and `output_python/` holds a fresh 248-tracker run (84,407 monthly rows).
The 172-vs-174 gap above is from the old snapshot and needs re-checking
against these new file counts. A fresh comparison already exists at
`output/comparison/2026-08-11T232419Z/` (`snapshot_patient_data_raw.json`,
`snapshot_patient_data_cleaned.json`) — use that rather than the `/tmp`
reports the original session produced, which no longer reflect the current
tracker set.

## Question

Run `just compare-outputs` against the USB drive's `output_r`/`output_python`
for `patient_data_raw` and `patient_data_cleaned` (a fresh run already
exists at `output/comparison/2026-08-11T232419Z/` — re-run only if working
this ticket long after that point, since the tracker set may have grown
further), and go through the flagged per-column differences the way
ticket 18 did for product: look for systematic patterns, fall back to the
real source Excel trackers as the arbiter, and add named causes to
`src/a4d/migration/compare.py`'s classifier registry as patterns are
confirmed (there is currently no `PATIENT_*_CLASSIFIERS` registry at all —
this ticket would create the first one, if warranted). This ticket is large
(patient has more columns and a longer history than product) — if it
doesn't converge in one session, split further rather than leaving it
open-ended, per the pattern ticket 18 itself used.

## Resolution

**Decision:** the patient raw-stage mismatch dominant cause is the same
date-representation artifact ticket 20 fixed for product's raw
`product_entry_date`. Extended `normalize_date_column` to the patient
`Patient (raw)` stage in `scripts/compare_outputs.py`, using the cleaned
schema's own `get_date_columns()` helper (18 `pl.Date` columns) rather than
a hand-maintained list. Did not touch pipeline code — comparison tooling
only.

**Because:** a re-run of the fresh 248-tracker comparison (a newer run than
the premise's referenced `2026-08-11T232419Z` snapshot already existed
locally at `output/comparison/2026-08-12T085925Z/`, so that was used
instead of triggering another full pipeline pass) showed patient raw-stage
mismatches concentrated almost entirely in date columns (`dob`: 79,836;
`last_clinic_visit_date`: 73,490; `fbg_updated_date`: 61,832;
`hba1c_updated_date`: 61,769; `bmi_date`: 61,765; `recruitment_date`:
51,605; `t1d_diagnosis_date`: 47,047; etc. — 17 of 18 schema date columns
appeared in the top of the list). A direct file check (`dob` on
`06 00GS Quirino Memorial Medical Center A4D Tracker_Jun_26`) confirmed the
exact pattern: R holds the unparsed Excel serial (`"39490"`), Python holds
the already-ISO-parsed date (`"2008-02-12 00:00:00"`).

**Rejected:** doing the full per-column triage for both raw and cleaned in
one session, as the ticket originally scoped — killed by scale, not by a
premise problem. After the date fix, raw-stage mismatches dropped from
564,096 to 46,788 (91.7%) across 70 -> 67 columns, but 46,788 across 67
columns is still not a one-session triage, and the cleaned stage (120,639
across 61 columns, confirmed unaffected by this fix) is untouched and
larger still. Split into [ticket 27](27-triage-patient-raw-residual.md)
(raw residual, with two leads already noted: `complication_screening`
looks like a genuine multi-select extraction gap, and `meter_received_date`
is a raw-only date column the schema-derived list didn't catch) and
[ticket 28](28-triage-patient-cleaned.md) (cleaned stage, untouched).

**Evidence:** executed — verified end-to-end against the real 248-tracker
drive comparison (before/after snapshots diffed directly), a direct
parquet-level check of the raw representation difference, `uv run pytest
tests/test_migration` (83 passed), and `ruff check` clean. No pipeline code
changed, only `scripts/compare_outputs.py` (comparison tooling).

**Tense:** all claims describe current, verified behaviour — not a
proposed design.
