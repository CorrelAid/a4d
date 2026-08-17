---
id: 43
title: Triage the residual patient raw-stage column mismatches (round 3)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-17b
claimed_at: 2026-08-17
resolution: decided
evidence: executed
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

## Resolution

**Decision.** Two of the residual's causes are settled and fixed; the largest
remaining one is a comparison-tool alignment failure, split into [ticket
45](45-patient-row-alignment-duplicate-keys.md). Patient raw-stage
unclassified fell **1,879 -> 1,409 (-25%)**, total raw mismatches 27,980 ->
27,510, measured against the new baseline run
`output/comparison/2026-08-17T192144Z`.

**1. Float-to-string rounding, 434 rows -- a tool gap, not a divergence.**
`fbg_baseline_mg.static` (192), `fbg_baseline_mmol.static` (110),
`complication_screening_lipid_profile_cholesterol_value` (72) and
`complication_screening_kidney_test_value` (60) were reported purely because
R writes `9.3000000000000007` where Python writes `9.3`. The existing
`normalize_numeric_column` already handles this; it never reached these four
because `PATIENT_RAW_NUMERIC_NORMALIZE_COLS` derived from the *cleaned*
schema, which has no entry at all for the Patient List join's `.static`
copies and types a screening measurement as a string (the column can also
hold "normal"). Replaced with `numeric_normalize_targets` (every raw column
except the join keys and `__` helpers), which is safe because
`normalize_numeric_column` passes non-numeric text through untouched.
**Verified rather than assumed**: across all 27,980 raw-stage mismatches
exactly 434 had both sides parsing to the same float, all four in those
columns -- so widening equality changed nothing else, and the re-run
confirmed it (all four -> 0, no other column moved by more than 6).

**2. Phantom patient rows, a real Python data invention -- fixed.**
`read_patient_rows` accepted any row where the row number (column A) *or* the
patient_id (column B) was present. `2024_Vietnam National Children`'s `Jul24`
sheet carries a bare list of patient IDs in rows 165-188 below the real data
block -- **exactly two non-empty cells each, the ID repeated, and nothing
else across 40 columns** (read directly from the source workbook). Python
emitted all 24 as monthly records, which then picked up real-looking
demographics from the Patient List join. R never sees them: its data block is
`which(!is.na(tracker_data[, 1]))`, the row-number column alone
(`script1_helper_read_patient_data.R`).

Adopting R's rule outright would have been wrong, and measuring stopped that.
A sweep of all 254 trackers found only **41** rows Python accepts past R's
numbered block, in 8 files: 36 are ID-only leftovers, 4 are template filler
(`patient_id = "0"`, already dropped by both pipelines -- verified in both
output parquets), and **1 is a complete patient record R loses** --
`2024_Mahosot` `Jun24` `LA-MH088`, 24 populated cells, which simply never got
a row number. So the fix keeps the case the `or` was written for and drops
only rows carrying no value beyond a repeat of their own identifier
(`_carries_data_beyond_identifier`). Deliberately not a cell-count threshold:
the trackers repeat the identifier in a second column, so "more than n
non-empty cells" would be a guess about layout. Verified end-to-end on the
real 248-tracker data: that file's `py_unmatched` rows went **24 -> 0**.

**3. `hba1c_updated`/`fbg_updated_mg` interior space, 86 rows -- Python is
right, R's mechanism unlocated.** All 86 are in `2017_Yangon Children's
Hospital`, shape `8.8(20.9.16)` R-side vs `8.8 (20.9.16)` Python-side. Read
the source cell directly (`Feb17`, row 62, column 12): **the workbook
contains `8.8 (20.9.16)`, with the space**. Python reproduces the source
exactly; R drops it. Searched R's raw path for the cause and did not find it
-- `sanitize_str` only touches column names and validator lookups, the
multiline-header merge only touches headers, and the wide-format splitter is
product-side. Recorded as understood-but-unlabelled rather than closed with a
guessed cause, per the map's standing bar; the classifier is left to ticket
46 along with the rest of the tail.

**Because.** The map's bar is deciding, not labelling, and the two items
worth deciding both turned on evidence a shape-match would have got wrong.
Cause 1 looked like a real divergence and was a tool gap; cause 2 looked at
first like Python dropping a month of data for 27 patients (the ticket's own
bidirectional-null signature) and was the reverse -- Python inventing rows.

**Rejected.**
- *Adopting R's "row-number column defines the block" rule.* Simplest and
  matches R exactly, but measured to lose `LA-MH088`, a real record. Rejected
  on evidence, not taste.
- *A non-empty-cell-count threshold to spot phantom rows.* Would have worked
  on today's data (2 cells vs 24) but is an invented constant about layout,
  the same objection ticket 42 raised against its 35 mmol/L threshold.
- *Extending `normalize_numeric_column` by hand-listing the four columns.*
  Rejected under the map's never-hand-maintain-a-derivable-list rule; the
  derivation was pointed at the wrong schema, so the derivation got fixed.
- *Chasing the remaining 808 fan-out rows in this session.* They need the
  patient arm to gain an ordinal row key, which is ticket 17's product work
  repeated with its own verification burden -- a separate piece, split rather
  than sprawled.
- *Classifying the Yangon 86 now.* Python is verified right, but naming a
  cause for a mechanism not located in R would cement a guess.

**Evidence.** All **executed**: the source workbooks read cell-by-cell
(VNC `Jul24` rows 165-188, Mahosot `Jun24` row 380, Yangon `Feb17` row 62),
the 254-tracker sweep, both output parquets checked for the filler rows, a
full `a4d run patient --force` re-run against the real 248-tracker set, and a
full comparison re-run. Full suite 717 passed, 1 skipped; ruff and
`ty check src/` clean. The one **read**-only claim is R's block-bounding rule,
taken from `script1_helper_read_patient_data.R` rather than by running R --
but its consequence (R has no `LA-MH088` row, and none of the 24 phantom
rows) was confirmed in R's own frozen output parquet.

**Tense.** Every count above is current behaviour measured after the fixes,
except the 1,879/27,980 starting figures, which describe the prior baseline
`2026-08-16T231826Z`.

**What is left.** 1,409 unclassified: 808 in three duplicate-key files
(ticket 45) and ~600 in the long tail (ticket 46).
