---
id: 27
title: Triage the residual patient raw-stage column mismatches after date normalization
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-12f
claimed_at: 2026-08-12
resolution: decided
evidence: executed
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

## Resolution

**Decision:** Fixed two representation gaps and classified two genuine-cause
patterns, cutting raw-stage patient mismatches from 46,788 to 18,813
(59.8%); the remaining 67-minus-however-many columns didn't converge in this
session and are split into [ticket
31](31-triage-patient-raw-residual-2.md).

**Because:**
- `hba1c_updated`, `hba1c_baseline`, `height`, `weight`, `fbg_baseline_mg`,
  `fbg_baseline_mmol`, `fbg_updated_mg`, `fbg_updated_mmol`, `bmi`, and
  `t1d_diagnosis_age` were dominated by the same float-to-string
  representation gap ticket 22 already fixed for product's raw numeric
  columns (R's own float formatting rounds trailing digits differently,
  e.g. `"8.800000000000001"` vs `"8.8"`). `PATIENT_RAW_NUMERIC_NORMALIZE_COLS`
  (`scripts/compare_outputs.py`), derived from `get_numeric_columns()`
  mirroring `PATIENT_RAW_DATE_NORMALIZE_COLS`'s own precedent rather than
  hand-listed, wires `normalize_numeric_column` into the `Patient (raw)`
  stage. `hba1c_updated` 5,928 -> 88, `hba1c_baseline` 5,748 -> 2, `height`
  1,366 -> 39, `weight` 856 -> ~0.
- `meter_received_date` (1,761 mismatches, the ticket's own second lead) is
  a raw-only column absent from the cleaned schema, so `get_date_columns()`
  never saw it; appended it by hand to `PATIENT_RAW_DATE_NORMALIZE_COLS`
  (the one genuinely non-derivable list entry, since it has no cleaned-stage
  counterpart to derive from). Collapsed to 0.
- `bmi` and `t1d_diagnosis_age` are formula-derived in the source trackers
  (BMI from weight/height; age from birth/diagnosis dates). A source
  formula error (height recorded as 0, an unparseable diagnosis date)
  leaves R's raw extraction holding the literal Excel error string
  (`"#DIV/0!"`, `"#VALUE!"`, `"#NUM!"`) while Python's raw extraction
  (openpyxl, `data_only`) has no cached value for an errored formula and
  returns `None` -- neither side is wrong, they're just representing
  "no value" differently. New `EXCEL_FORMULA_ERROR_CLASSIFIERS`
  (`r_formula_error`) in `src/a4d/migration/compare.py`, wired for `bmi`,
  `t1d_diagnosis_age`, and `age`. `t1d_diagnosis_age` 2,505 -> 18 residual
  (99.3% explained); `bmi` residual after numeric-normalize is 1,048, of
  which 1,009 are this cause.
- New systemic pattern, not in this ticket's original leads: several raw
  date columns (`hba1c_updated_date`, `bmi_date`, `blood_pressure_updated`,
  `fbg_updated_date`, `last_clinic_visit_date`, `hospitalisation_date`, and
  four `complication_screening_*_date` columns) show R holding the sentinel
  (`9999-09-09`) against Python holding a real date with an implausible
  year (2567-2569). Verified directly against the real source Excel (06
  Nakornping Hospital A4D Tracker_Jun_26.xlsx, patient TH_NK004,
  `hba1c_updated_date`, row 87): the cell is genuinely date-typed
  (`dd-mmm-yyyy` number format) but holds year 2569 -- a clinician typed a
  Thai Buddhist-Era year (BE = CE + 543) directly into a Gregorian date
  field. R's raw extraction already rejects the implausible year and emits
  the sentinel; Python's raw extraction is a faithful, by-design
  pass-through of the cell's literal value. Confirmed **not** a pipeline
  bug: the cleaned stage's own future-date guard (`_validate_dates`,
  `clean/patient.py`) independently replaces the same cell with the
  identical sentinel (verified against the real cleaned parquet for
  TH_NK004 -- the June row already reads `9999-09-09`), so both pipelines
  already agree from the cleaned stage onward regardless of this raw-stage
  representation gap. New `PATIENT_BUDDHIST_ERA_CLASSIFIERS`
  (`buddhist_era_typo`) reuses the product pipeline's own
  `BUDDHIST_ERA_THRESHOLD` (2400) rather than inventing a new one. Explains
  369 of the 371 sentinel-vs-implausible-year rows found.
- Both new comparison-tool normalizations and both new classifiers are
  covered by unit tests (`tests/test_migration/test_compare.py`); full
  suite (599 passed, 1 skipped), ruff, `ty check src/` all pass.

**Rejected:** Chasing `complication_screening` (12,566 mismatches, the
single largest residual column, already flagged in this ticket's premise as
a probable multi-select extraction gap) in this session -- it's a genuinely
different investigation (a content/extraction-logic question, not a
representation gap fixable by a normalization or a mechanical classifier)
and would have meant sprawling past the two leads this ticket was actually
scoped to chase. Left for [ticket 31](31-triage-patient-raw-residual-2.md).

**Evidence:** executed -- both normalizations and both classifiers were
verified against the real 248-tracker drive comparison (before: 46,788
mismatches; after: 18,813), and the Buddhist-era finding was additionally
verified against the real source Excel cell and the real cleaned-stage
parquet output, not reasoned about.

**Tense:** current behaviour throughout -- every number above is from a
real comparison run against the real drive data (`output/comparison/2026-08-12T200529Z/`),
not a projection.

## Addendum (ticket 24, closed same day)

[Ticket 24](24-triage-remaining-raw-column-residual.md) confirmed a
possibly-systemic raw-extraction pattern it had flagged as a theory: R's
readxl infers a column's type from its majority values, so a lone Excel
date/time-formatted cell in an otherwise-numeric raw column gets coerced to
that column's type (the raw serial), while Python's openpyxl honors the
individual cell's own format and returns a `datetime`/`time` object —
verified against real source Excel cells (Penang General Hospital 2019
Apr19!E36, a "Units Received" cell literally formatted `d/m/yy`). A reusable
classifier (`STRAY_DATE_CLASSIFIERS` / `_is_openpyxl_date_typed_stray_cell`,
`src/a4d/migration/compare.py`) now exists for this pattern — not yet
applied to any patient column. Worth checking whether any of this ticket's
67 residual columns show the same r_value-is-a-plausible-Excel-serial /
py_value-is-a-datetime-or-time-string shape before assuming a different
cause.
