---
id: 63
title: The cleaned stage has 4,949 cells with no cause, because the ID spelling that explains them is gone by then
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-24e
claimed_at: 2026-08-24T22:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 58
---

## Premise

Rests entirely on [Monthly rows with a misspelled ID silently lose their
Patient List demographics](58-patient-list-join-uses-unfixed-id.md), closed,
which made both whole-tracker joins key on a normalized `patient_id` and so
recovered 680 rows / 6,863 Patient List cells that R still publishes as null.

That decision also established the constraint this ticket exists inside: the
new cause `r_static_join_misses_respelled_id` can only fire on the **raw**
stage, because its discriminator is the month row's own ID still carrying the
hyphen or transfer-clinic suffix -- and cleaning normalizes exactly that, on
both sides. Raw-stage `unclassified` is now **0**; cleaned-stage went **16 ->
3,593**.

Also rests on the map's standing bar (**triage means deciding, not
labelling**): a cause carrying the right label over the wrong reason is what
[ticket 62](62-finish-the-pre-bar-classifier-audit.md) found three times over,
so widening `r_extraction_gap` to swallow these is explicitly not the answer.

**What would void this ticket rather than rewrite it:** ticket 58's join fix
being reverted, since without it these 3,593 cells do not exist.

## Question

1. **Find a discriminator that survives cleaning.** Candidates: have the
   comparison carry the raw spelling forward as a diagnostic flag on
   `CellMismatch` (the shape `row_order_candidate` and
   `group_endpoint_matches` already use); or derive the affected identities
   once per file and match on those; or have cleaning record the
   pre-normalization ID in a column. Each has a different reach -- the first
   two touch only the comparison, the third changes production output.
2. **Bound the three columns the corpus-wide wiring over-claimed on.** Ticket
   58 measured that `t1d_diagnosis_age` (1,069 rows against a join-miss
   population of 679), `bmi` (144) and `age` (1) also carry R-null/Python-present
   cells for these patients from some *other* mechanism, because the month
   sheets carry those columns too. They currently keep their pre-existing
   causes. Measure what those other rows actually are and whether their
   current cause states the right reason -- this is a ticket-32-shaped
   question, not a wiring question.
3. **Check what absorbed the new cells before the bounded wiring landed.**
   `recruitment_date` went 28,085 -> 28,762 in the first post-fix comparison
   with no `unclassified` movement, which means an existing cause
   (`r_extraction_gap`, whose documented mechanism is R's `xml:space` header
   defect) silently took 677 cells that belong to the join miss. Confirm no
   other column is still in that state on the cleaned side.

## Standing bar

Per the map's **triage means deciding, not labelling**: measure before
proposing, and a classifier is only written once the mechanism is traced.

## Resolution

**Decision.** The discriminator is derived per file from the run's own **raw**
output, comparison-side only (question 1's first candidate). `static_join_missed_ids`
(`src/a4d/migration/compare.py`) reads each raw parquet's `patient_id` column
and returns the *normalized* spelling of every ID that was written
non-canonically -- the last place the two spellings coexist. `compare_cells`
sets `CellMismatch.static_join_missed_id` from that set, and
`_is_r_static_join_misses_respelled_id` accepts it as an alternative to the raw
stage's own per-cell test. Production output is untouched.

**The ticket's headline number was understated.** It said cleaned
`unclassified` went 16 -> 3,593. Measured across the four snapshots of
2026-08-24: it is **16 -> 4,949**, stable over five runs. Raw is 0. Ticket 58's
framing survives; only its size was wrong, and the title is corrected.

**Two guards had to be added before the cause was true, and both were found by
measuring rather than by reasoning.**

1. **A column R lost across the whole file is a different mechanism.** Wired
   naively, the prepended cause claimed 9,302 cells across **43 files** -- far
   beyond the 6 files ticket 58 recovered. 2024 Preah Kossamak reads **zero**
   `recruitment_date` in 863 rows and 2024 Yangon General zero in 1,057, which
   is `r_extraction_gap`'s file-level `xml:space` header defect (ticket 62);
   2024 Mahosot reads 672 of 1,068, so *its* nulls really are per-patient. New
   `CellMismatch.r_column_empty_in_file`, measured on R's own frame, makes the
   cause decline the first case. It removed 2,336 cells whose reason is R's
   header, not R's key -- the exact ticket-32 failure mode of a right label
   over a wrong mechanism. The raw stage never needed it: a column R never
   mapped is absent there and is reported as column divergence.
2. **`age` is derived, so it needed its own cause, not this one.** New
   `r_age_not_derived_without_dob`, wired to `age` alone and keyed on new
   `CellMismatch.row_dob_recovered` (this row's `dob` null on R, present on
   Python) rather than on the file-level set -- the birth date is what the
   derivation actually consumes.

**Question 2 is answered, and two of its three columns needed nothing.**
- `age`: **113 cells**, all on join-miss identities, in 3 files. 53 differ
  numerically (-2, -1, +1, +4) and 60 are R-null. One mechanism for both:
  `_fix_age_from_dob` overrides the sheet's Age cell with the D.O.B.-derived
  age; R's `dob` is null for **all 275 rows** of the affected patients in its
  frozen 2023 Mahosot output, so R keeps the clinic's typed figure or nothing.
  LA_MH060's recovered D.O.B. is 2009-01-16, so `Jan23` is 14 -- Python's
  value; R publishes 13, the clinic's own, updated a month late. **Python is
  the correct side.**
- `bmi`: **0 cells** on join-miss identities in the current cleaned
  comparison. Ticket 58's measured 144 does not survive; nothing to bound.
- `t1d_diagnosis_age`: 1,078 cells on these identities, on
  `r_never_derives_diagnosis_age` (683), `r_numeric_error_sentinel` (391) and
  `source_date_in_diagnosis_age` (4). The reason is **right but was
  incomplete**: these are divergences ticket 58 *created* (2024 Mahosot's
  LA_MH056 is null on `dob`, `t1d_diagnosis_date` and `t1d_diagnosis_age` in R
  and 2014-02-22 / 2021-06-22 / 7 in Python), yet R would publish nothing here
  even holding both dates, because its `fix_t1d_diagnosis_age` call site is
  commented out. Docstring corrected; **no count moved** -- ticket 62's shape.

**Question 3 is answered, and more was absorbed than the ticket suspected.**
It flagged `recruitment_date` (677). Measured, four causes were silently
holding join-miss cells on the cleaned side, and the guard-corrected
reassignment is: `recruitment_date|r_extraction_gap` 28,686 -> 28,015 (671),
`fbg_baseline_mg|r_join_suffix_collision` 9,521 -> 8,844 (677),
`edu_occ|r_extraction_gap` 283 -> 59 (224), `edu_occ_updated|r_extraction_gap`
2,993 -> 2,769 (224), and `blood_pressure_{sys,dias,updated}|r_extraction_gap`
21 -> 12 (9 each). Every one of those now matches the **raw** stage's count for
the same column cell-for-cell (671, 677, 223, 223, 8), which is the strongest
available evidence the reassignment is right: two independently-derived
discriminators agreeing.

**Rejected.**
- *Publishing the pre-normalization ID as a cleaned column* -- the most direct
  discriminator, but it changes the 83-column schema that matches R's output,
  a production change serving a migration-only tool due to be deleted with R.
- *Emitting an error record when the pipeline normalizes a join key* -- cleaner
  provenance, but it adds a production error record with no consumer after
  retirement and needs a full 254-tracker re-run before the comparison sees it.
- *Widening `r_extraction_gap`* -- explicitly ruled out by the premise, and the
  measurement above shows why: it was already absorbing 4,482 cells under the
  wrong reason.
- *Excluding an ambiguous identity from the set.* 2026 Surat Thani spells the
  same patient both `TH_ST029` and `TH-ST029` in `May26`; after normalization
  the two rows are indistinguishable, so 5 cells (1 row x 5 columns) are
  claimed that the raw stage labels `r_extraction_gap`. Excluding the identity
  would cost two correct classifications to avoid one wrong one, so it is named
  in the docstring instead.

**Evidence: executed.** Every count above is from a real 254-tracker comparison
against the frozen R baseline on the USB drive, not from reading code. The two
source workbooks (2026 Surat Thani's `Patient List` and `Annual`) were opened
directly; R's and Python's frozen parquets were queried for the D.O.B. and
diagnosis-date claims. Full suite 980 passed / 1 skipped; ruff clean; `ty`
unchanged at 44 pre-existing diagnostics (verified by stashing).

**Tense.** Every count describes current behaviour after this session's change,
except the "before" figures, which describe the run at `2026-08-24T182929Z`.

**Result: cleaned `unclassified` 4,949 -> 16, the pre-session baseline; raw
stays 0; both product stages unmoved; and the four-stage total is unchanged at
121,742 / 33,488 / 22,735 / 89 -- so nothing was invented, lost, or quietly
pushed into the unexplained bucket.** The 16 remaining are the pre-existing
cells owned by fog patches (11 `insulin_subtype`, 2 `fbg_updated_mmol`, 2
`remote_followup`, 1 `bmi_date`).
