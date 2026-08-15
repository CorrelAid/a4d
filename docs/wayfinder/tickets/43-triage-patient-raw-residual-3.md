---
id: 43
title: Triage the residual patient raw-stage column mismatches (round 3)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 31
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches (round
2)](31-triage-patient-raw-residual-2.md), closed: the stage's dominant column
`complication_screening` is fully resolved, in two separate halves. A real
Python data loss was fixed -- `ColumnMapper.rename_columns` kept only the
first of several source columns mapping to one canonical name, discarding
2,489 recorded values across 27 trackers; it now merges them the way R's
`tidyr::unite()` and the pipeline's own `merge_duplicate_columns_data()` do.
And R's `NA` padding from that same unite (its `na.rm` defaults to `FALSE`)
became the source-verified `r_na_unite_padding` classifier. Patient raw-stage
unclassified fell 14,903 -> 1,879 (-87%) against baseline run
`output/comparison/2026-08-15T214447Z`.

Also rests on [Triage the patient pipeline's raw-stage column-existence
divergence](30-triage-patient-raw-column-divergence.md), closed, for the
`insulin_regimen` lead below; and on the map's standing scoping rule that the
current tracker template is the golden rule, so a column that appears in one
year and is gone the next is not worth chasing.

Overturning ticket 31's merge decision would void this ticket rather than
require rewriting it -- several of the shapes below exist only because the
merge now happens.

## Question

Triage the remaining **1,879 unclassified** raw-stage mismatches across
roughly 50 columns, none larger than 235. Continue the pattern tickets
20/21/22/24/27/31 established: find systematic shapes, arbitrate against the
real source Excel, add named causes to the `PATIENT_*_CLASSIFIERS` registries
in `src/a4d/migration/compare.py` -- and, per the map's standing bar, decide
whether Python is doing the right thing rather than only labelling.

Three shapes are already visible and should be checked first:

- **`insulin_regimen` (235), and the trap in it.** 194 of the 235 rows are in
  `2021_Kantha Bopha` and are ticket 30's source-verified blank-header
  recovery: R keeps those values only as a junk-named `na1` column, Python now
  recovers them, so R is null where Python has a verified value. The other 41
  rows (39 in `2024_Vietnam National Children`, 2 in `2023_...`) share the
  *shape* but were never verified. Ticket 31 deliberately did **not** wire this
  column to `r_extraction_gap`, because that classifier fires on any
  R-null/Python-present cell and would have labelled the unverified 41 without
  deciding them. Verify the 41 against source before choosing a cause, or split
  the classifier so it fires only where the evidence reaches.
- **`observations` (61) -- two shapes, one of them new.** R carries a trailing
  space on a sub-value before the join (`"Normal ,Insulin"` where Python has
  `"Normal,Insulin"`), because ticket 31's merge strips each part while R's
  `unite` does not. This is interior whitespace, so the existing
  `normalize_whitespace_column` (which trims whole values) does not reach it --
  decide whether to extend it or classify. The rest are `NA,NA` on R's side
  against a real Python value (`"TSH"`, `"Foot Examination (Nerves)"`), which
  looks like the ticket-31 recovery reaching a column R lost entirely.
- **`fbg_baseline_mg.static` (192) and `fbg_baseline_mmol.static` (110).**
  Never looked at by any ticket. The `.static` suffix is the Patient List join
  suffix, so `PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS` and the assumption in
  force about which baseline-FBG copy Python keeps are both directly relevant
  -- read them before measuring.

The rest is a long tail: `hba1c_updated` (88), `last_clinic_visit_date` (88),
`fbg_updated_date` (75), `complication_screening_lipid_profile_cholesterol_value`
(72), `complication_screening_kidney_test_value` (60), `status` (49),
`observations_category` (48), `insulin_injections` (46), and ~40 more under 45
each. Ticket 31's early sampling of some of these predates two extraction
changes (ticket 30's blank-header recovery and ticket 31's merge), so
re-measure rather than trusting the old characterizations.

Split further rather than leaving this open-ended if it does not converge.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict
on whether Python is right, with the evidence. Where Python is losing
information the source carried, fix the pipeline (tickets 27, 30 and 31 all
turned out to be that). Where the source workbook itself is wrong, that is a
legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md), not a pipeline fix. A cause
genuinely undecidable on the available evidence is recorded as an open
question, not closed with a label.
