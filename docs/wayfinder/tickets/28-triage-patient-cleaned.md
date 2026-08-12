---
id: 28
title: Triage the patient cleaned-stage column mismatches
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-12c
claimed_at: 2026-08-12
resolution: decided
evidence: executed
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

## Resolution

**Decision:** root-caused and resolved three of the five dominant columns;
the rest (56 smaller columns plus residuals on the three resolved ones)
didn't converge and split into [ticket 29](29-triage-patient-cleaned-residual.md),
per this ticket's own pre-authorization to split.

**t1d_diagnosis_age (25,968 mismatches, the single largest column) was a
real Python bug, now fixed.** `_fix_t1d_diagnosis_age`
(`src/a4d/clean/patient.py`) unconditionally recomputed the value from
`dob`/`t1d_diagnosis_date`, discarding any real recorded age whenever either
date failed to parse -- its docstring's justification ("Matches R... like R
pipeline does") is false: R's own `fix_t1d_diagnosis_age`
(`script2_helper_patient_data_fix.R`) is dead code, never called from
`script2_process_patient_data.R` (the call site is commented out), so R
always just keeps the raw recorded value untouched. Confirmed via the
dominant mismatch pattern: 16,874 of 25,968 rows had R holding a plausible
1-20 age with Python null, plus 3,188 rows off by exactly 1 -- both point at
Python discarding/overriding real recorded data, not R being wrong. Fixed to
prefer the raw recorded value whenever present and not the Excel error
sentinel (999999), falling back to date-based calculation only when the raw
value is genuinely missing. Two new regression tests added
(`tests/test_clean/test_patient.py`); the existing sentinel-replacement test
still passes unchanged. Verified against the real 248-tracker drive data: a
full patient pipeline re-run (`a4d run patient --force`) and comparison
re-run confirm the column's mismatches dropped 25,968 -> 4,807 (81.5%), with
the full pipeline test suite (585 tests), ruff, and `ty check src/` all
passing. The 4,807 residual is unclassified and left for ticket 29.

**recruitment_date (28,512) and insulin_subtype (15,724) are genuine, already-
intentional Python-correct divergences -- classified, not "fixed", since
there's nothing to fix.** `recruitment_date`: spot-checked directly against
the real source Excel (Quirino Memorial Medical Center, patient PH_QM001) --
the tracker's own "Patient List" sheet plainly records
"Date of Recruitment" = 2025-12-01; Python extracts it correctly, R's static
extraction leaves it null. A new `r_extraction_gap` classifier
(`PATIENT_RECRUITMENT_DATE_CLASSIFIERS` in `src/a4d/migration/compare.py`)
explains 28,010/28,512 (98.2%) of this column's mismatches.
`insulin_subtype`: already documented as a deliberate, verified-correct
Python divergence in `_derive_insulin_fields`'s own docstring
(`src/a4d/clean/patient.py`) -- R's own allowed-values validator rejects the
multi-insulin CSV string R's own derivation logic produces for 2024+
trackers, replacing it with the "Undefined" sentinel; Python's derivation is
correct and fixes a known R typo besides. A new
`r_validator_rejects_multivalue` classifier
(`PATIENT_INSULIN_SUBTYPE_CLASSIFIERS`) explains 15,656/15,724 (99.6%).
Neither classifier changes pipeline behavior -- both are compare-tool-only,
wired into `CLASSIFIERS_BY_COLUMN` in `scripts/compare_outputs.py`. Four new
unit tests added (`tests/test_migration/test_compare.py`, 91 passing).

**insulin_total_units (16,985) and fbg_baseline_mg (9,041) were
investigated but did NOT converge to a confirmed root cause** -- both show
R null / Python real-value for the large majority of rows (16,985/16,985
and 8,883/9,041 respectively), consistent with the same "Python fills an R
extraction/conversion gap" class as the two resolved columns above, but
unlike them this wasn't verified against the real source Excel or code
(`insulin_total_units` has no cleaning-stage transform at all on either
side, and its raw-stage comparison shows 0 mismatches, meaning whatever
causes the divergence happens during R's or Python's *type conversion* step,
not extraction -- not yet traced to a specific line). Left unclassified;
carried into ticket 29 rather than guessed at.

**Rejected:** closing this ticket only when all 61 columns converge -- the
ticket's own premise pre-authorized splitting, and forcing convergence here
would mean either rushing the unconfirmed `insulin_total_units`/
`fbg_baseline_mg` hypotheses into classifiers without source verification
(against this map's own verification standard) or leaving genuine progress
on the table waiting for the other 56 columns none of which were even
sampled yet.

**Evidence:** executed -- the `t1d_diagnosis_age` bug fix was verified with
a real 248-tracker pipeline re-run and comparison re-run (not just unit
tests); the `recruitment_date` root cause was verified against the real
source Excel tracker directly, not inferred from the data pattern alone.
`insulin_subtype`'s root cause is `read`-tier evidence (confirmed via
existing code comments/docstring, not independently re-derived this
session) but is itself already load-bearing on a prior, executed
verification (the code comment cites a specific R typo and validator
behavior). `insulin_total_units`/`fbg_baseline_mg` have no classifier and
carry no evidence claim.

**Tense:** all pipeline-code claims (the fix, the docstring's incorrect
justification, R's dead code) describe current committed behavior as of this
session, not a proposal.
