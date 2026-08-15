---
id: 31
title: Triage the residual patient raw-stage column mismatches (round 2)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-15b
claimed_at: 2026-08-15
resolution: decided
evidence: executed
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

## Premise update (session-2026-08-14, ticket 37's session)

Two things moved under this ticket without changing what it asks:

- **The tracker set is now 254 files, not 248**, and the frozen R baseline
  was renamed to match a bulk `06 ... -> 2026_...` rename by the data analyst
  (see [ticket 37's addendum](37-triage-patient-cleaned-residual-2.md)). The
  numbers below supersede this ticket's original ones, and the baseline run
  is `output/comparison/2026-08-14T200342Z`, not the 2026-08-12 snapshot the
  Question cites.
- **Ticket 37's date-parser fixes reach this stage too.** The raw-stage
  comparison normalizes both sides with `normalize_date_column`, which calls
  the same `parse_date_flexible` ticket 37 fixed three times over (the broken
  month-name truncation, the 2-digit-only month-year branch, and the new
  longest-parseable-prefix fallback). So some of this ticket's residual has
  already moved without anyone triaging it.

Current raw-stage figures: **27,921 mismatches, 14,844 unclassified** (was
28,033 / 14,981). `complication_screening` remains the dominant single
column and this ticket's main question is unchanged.

Also inherited from ticket 37: **13 cleaned-stage rows were found where both
pipelines hold the same two rows in a different order**, because
`patient_id` + `sheet_name` is duplicated for that patient in that sheet --
the same "swapped adjacent row" shape this ticket's Question already lists in
its long tail. [Ticket 38](38-triage-patient-cleaned-date-family.md) now owns
deciding whether patient's row-alignment key needs product's positional
treatment; whatever it decides settles this ticket's version too, so do not
re-derive it here.

## Premise update (session-2026-08-14b, ticket 38's session)

**The row-alignment question this ticket deferred to [ticket
38](38-triage-patient-cleaned-date-family.md) is answered: patient's key stays
as it is.** Measured across all 254 cleaned files, 84 of 85,325 rows (0.10%),
in 7 files, sit on a duplicated `patient_id` + `sheet_name`. Product's key was
broken in a different league (up to 35-way duplication) before ticket 17 gave
it `add_row_ordinal`. Do not re-derive this; the "swapped adjacent row" shape
in this ticket's long tail is that bounded 84-row population.

**Two of ticket 38's changes move this stage's numbers without anyone having
triaged them.** The raw-stage comparison normalizes both sides with
`normalize_date_column`, which calls `parse_date_flexible` -- and ticket 38
widened its missing-marker handling (`MISSING_VALUE_MARKERS`,
`DATE_ABSENCE_MARKERS`, `DATE_PLACEHOLDER_FRAGMENTS`), so cells recording "-",
"Nil" or the template's placeholder text now normalize to null on both sides
rather than to the error sentinel. Current raw-stage figures: **27,893
mismatches, 14,816 unclassified** (was 27,921 / 14,844); the baseline run is
`output/comparison/2026-08-14T204031Z`. `complication_screening` remains the
dominant single column and this ticket's main question is unchanged.

## Resolution (session-2026-08-15b)

### Decision

**The dominant column is resolved, and it was a bug-fixing session, not a
labelling one.** `complication_screening` (12,566 mismatches, 84% of the
residual) had two entirely separate causes stacked on top of each other, and
the ticket's own headline lead was neither of them.

**Cause 1 -- a real Python data loss, now fixed.** `ColumnMapper.rename_columns`
(`src/a4d/reference/synonyms.py`) handled several source columns mapping to one
canonical name by keeping the first and dropping the rest, under a comment
calling it "an edge case from discontinued 2023 format". It is not an edge
case: the 2023 template splits complication screening across B.P./Kidney/Eye/
Foot/Lipids sub-columns that all map to `complication_screening`, and each
carries an independent value. Python kept B.P. and silently discarded the rest.
Measured by instrumenting the real extraction over all 254 trackers:
**2,489 recorded values dropped across 27 trackers** (2,457
`complication_screening`, 32 `observations`). Concretely, `KH_KB023` in
`2023 Kantha Bopha`'s `Jan'23` has `JAN` in the Kidney column and nothing
else, and Python emitted `null` for that patient-month.

The fix merges the group -- comma-joining non-empty values in column order --
which is what R's `tidyr::unite()` does and what `merge_duplicate_columns_data`
in the same pipeline already does for repeated *raw headers*. The
keep-first branch's misleading `invalid_tracker` warning is replaced by a
`duplicate_source_columns` warning naming the group, so a new duplicate group
is visible rather than silent (ticket 30's `blank_header_with_data` precedent).
Verified against the real files: `KH_KB023` now carries `JAN`.

**Cause 2 -- an R rendering artifact, correctly a classifier.** R's
`tidyr::unite(sep = ",")` leaves `na.rm` at its `FALSE` default, so every empty
cell in the group becomes the literal string `NA`: a patient screened in
January reads `JAN,NA,NA,NA,NA` and an unscreened patient reads
`NA,NA,NA,NA,NA` rather than being null. 99.3% of the column's mismatches carry
an `NA` token. This is R's rendering and carries no information --
source-verified against `2023 Kantha Bopha`'s `Jan'23!AB98-AF98`, where the
padded sub-columns are genuinely empty in the workbook. **Python is the correct
side.** New `r_na_unite_padding` classifier
(`PATIENT_NA_UNITE_PADDING_CLASSIFIERS`, `src/a4d/migration/compare.py`), wired
to the three canonical columns that form a duplicate group anywhere in the
254-tracker set -- derived by measurement, not hand-listed. It fires only when
stripping the `NA` tokens leaves exactly Python's value, so a real disagreement
inside a group stays unclassified.

**The ticket's headline lead was a 2-row phenomenon.** Ticket 27 flagged
`2021_NPH`'s "Python has a comma-joined multi-select where R has only the
first selection" as the likely systematic cause. Measured: **2 rows out of
12,566.** Do not re-propose it as the explanation for this column.

### Numbers (real 254-tracker drive data, baseline run `2026-08-15T214447Z`)

- Patient raw-stage **unclassified: 14,903 -> 1,879 (-87%)**.
- Total raw-stage mismatches 28,092 -> 27,980; the count barely moves because
  cause 1 recovers data on Python's side while cause 2's mismatches remain
  mismatches until classified. The two must not be judged by the same number.
- `complication_screening` 12,566 -> 2 unclassified;
  `latest_complication_screenning` 308 -> 0; `observations` 325 -> 61.
- Full suite 696 passed, 1 skipped; ruff and `ty check src/` clean.

### Rejected

- **Coalesce instead of concatenate** (take the first populated value per row).
  Killed on measurement: 1,393 rows have two or more populated sub-columns, so
  coalescing would still lose data.
- **A declared config list of mergeable canonical columns.** Rejected as a
  hand-maintained list that would drift; the merge rule is general, and the
  measurement showing only three targets ever collide is what makes it safe.
- **Keeping keep-first for identity columns as a guard.** No identity or scalar
  column forms a duplicate group anywhere in the 254 real trackers -- only
  `complication_screening`, `observations` and `latest_complication_screenning`
  (the last never populated). The `patient_id` scenario in
  `test_harmonize_patient_data_columns_multiple_synonyms` is synthetic, and its
  stated rationale ("This matches R behavior") was factually wrong: R unites.
  The test was updated rather than kept. What this gives up: if a future tracker
  ever populates two spellings of an identity column, they will be concatenated
  rather than one silently chosen. The new `duplicate_source_columns` warning is
  what makes that visible if it happens.
- **Chasing the long tail in the same session.** ~50 columns, largest 235, at
  least three distinct shapes -- a different investigation. Split out rather
  than sprawled, per the pattern tickets 18/27 set.

### Evidence

**Executed** for every load-bearing claim: the 2,489-value loss and the
1,393-multi-populated-row count come from instrumenting `read_all_patient_sheets`
over all 254 real trackers; the mechanism was read directly from
`r-archive/R/script1_read_patient_data.R` (`tidyr::unite`) and
`src/a4d/reference/synonyms.py`; the `KH_KB023` case was read cell-by-cell from
the real source workbook and re-checked in Python's output after the fix; all
before/after counts come from real pipeline and comparison runs against the
drive, not from unit tests.

**Tense:** every number above describes current behaviour after this session's
commits, except the 2,489-value loss and the pre-fix per-column counts, which
describe the behaviour this session removed.

### Not fixed, deliberately

The 1,879 remaining unclassified rows across ~50 columns, spawned as [ticket
43](43-triage-patient-raw-residual-3.md). Three shapes are already visible and
recorded there. In particular `insulin_regimen` (235) was **not** wired to
`r_extraction_gap` even though its shape matches: 194 of its rows are ticket
30's source-verified blank-header recovery, but the other 41 are not verified,
and firing a whole-column classifier on an R-null/Python-present shape would
label them without deciding them -- exactly what this map's standing bar
forbids.
