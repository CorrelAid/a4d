---
id: 29
title: Triage the residual patient cleaned-stage column mismatches
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 28
---

## Premise

Rests on [Triage the patient cleaned-stage column mismatches](28-triage-patient-cleaned.md),
closed: that ticket root-caused and resolved three of the five dominant
cleaned-stage columns (`t1d_diagnosis_age` -- a real Python bug, now fixed;
`recruitment_date` and `insulin_subtype` -- genuine Python-correct
divergences, now classified), dropping total cleaned-stage mismatches from
120,639 to 99,478. It explicitly split off the rest rather than force
convergence, per its own pre-authorization.

## Question

Triage what's left of the patient cleaned-stage mismatches (rerun `just
compare-outputs` against the current `output_r`/`output_python` on the USB
drive to get a fresh snapshot -- ticket 28's own run is now the baseline).
In priority order:

1. **`insulin_total_units` (16,985) and `fbg_baseline_mg` (9,041)** --
   ticket 28 found both are dominated by R-null/Python-has-value (matching
   the class already confirmed for `recruitment_date`), but didn't verify
   against source or trace the actual conversion-step code path. Both have
   no cleaning-stage transform on either side and 0 raw-stage mismatches,
   meaning the divergence is introduced during *type conversion*, not
   extraction -- worth checking whether R's `as.numeric()`-equivalent
   conversion step fails more aggressively than Python's on some value
   format (the parallel to `product_units_received`'s ticket-22 finding is
   worth checking first).
2. **`t1d_diagnosis_age`'s residual (4,807, post-fix)** -- unclassified;
   the fix only addressed the null-discard/off-by-a-few pattern, not
   whatever's left.
3. **`recruitment_date`'s residual (502) and `insulin_subtype`'s residual
   (68)** -- small, but worth a quick look since the dominant cause is
   already known and these are what's left after removing it.
4. **The other 56 columns** (up to ~4,504 mismatches each: `blood_pressure_updated`,
   `status`, `hospitalisation_date`, `hba1c_updated_date`, `fbg_updated_date`,
   `insulin_regimen`, `insulin_type`, ...) -- none sampled yet.

Same method as ticket 28: look for systematic patterns, fall back to the
real source Excel trackers as the arbiter (mount at `/Volumes/USB SanDisk
3.2Gen1 Media/a4d/`), and add named causes to
`PATIENT_*_CLASSIFIERS` registries in `src/a4d/migration/compare.py`
(`scripts/compare_outputs.py`'s `CLASSIFIERS_BY_COLUMN` wires them to
columns) -- or fix a real Python bug directly, as ticket 28 did for
`t1d_diagnosis_age`, when one turns up. This is likely to be large --
split further rather than leaving it open-ended if it doesn't converge in
one session.
