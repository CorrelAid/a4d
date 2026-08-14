---
id: 29
title: Triage the residual patient cleaned-stage column mismatches
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-13b
claimed_at: 2026-08-14T00:00:00+02:00
resolution: decided
evidence: executed
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


## Resolution (session-2026-08-13b)

**Decision.** The two priority columns are both R defects, not Python
divergences, and the 999999-sentinel family that runs through the whole
report is a deliberate and correct Python representation choice. Three
classifiers were added and two real Python bugs -- found while sampling the
long tail -- were fixed in the pipeline. Cleaned-stage mismatches fell
99,408 -> 95,490 and unclassified rows 55,670 -> 16,698 (-70%). What was
not chased is split into [ticket 37](37-triage-patient-cleaned-residual-2.md).

**Because.**

1. **`insulin_total_units` (16,985, all R-null) -- R never reads the column
   at all.** R's `extract_patient_data`
   (`r-archive/R/script1_helper_read_patient_data.R`) carries a hack for a
   merged-cell artefact that can produce two "insulin regimen" columns: it
   greps the source headers for the literal `Insulin` and drops every match
   after the first. Since the 2024 tracker redesign the monthly sheet also
   carries "TOTAL Insulin Units per day", so the grep matches two real,
   unrelated columns and the hack deletes the second. The sibling insulin
   columns survive only because their sub-headers read
   "Pre-mixed"/"Short-acting" (the "Human Insulin" group header sits in a row
   R does not merge here), and "Number of insulin injections" survives on a
   lowercase "i" the case-sensitive grep misses. Measured: R's cleaned output
   has **0 non-null values across all 81,859 rows**, and the column is absent
   from R's raw parquet entirely -- not even as an unmapped passthrough.
   Python has 18,341. Verified against the real source Excel (06 500 NPT
   Children's Hospital, `Jan26` header row 93 col 27 "TOTAL Insulin Units ",
   data rows 94-98 = 20, 48, 24, 30, 20 -- exactly Python's values). Python
   is not diverging; it is the only side that reads the column.
   Classifier: `r_insulin_dedup_drop`.

2. **`fbg_baseline_mg` (9,041) and `fbg_baseline_mmol` (1,156) -- R's
   Patient List join renames both sides on a name collision.**
   `reading_patient_data` (`r-archive/R/script1_read_patient_data.R`) joins
   the monthly sheets to the static "Patient List" sheet with
   `suffix = c(".monthly", ".static")`. Where a column exists on both sheets
   dplyr renames *both*, so the unsuffixed name disappears and R's cleaning
   stage -- which reads `fbg_baseline_mg` -- finds nothing and leaves the
   schema column null for the whole file. R avoids exactly this for
   `hba1c_baseline` by dropping the monthly copy before the join; it never
   does the same for the baseline FBG columns. Polars suffixes only the
   right-hand frame, so Python keeps the monthly value under the base name.
   Measured across the real drive data: 21 files carry
   `fbg_baseline_mg.monthly` and 3 carry `fbg_baseline_mmol.monthly`, and
   those files account for 8,883 of 9,041 and 1,101 of 1,156 mismatches
   respectively. Across their ~10,000 rows the monthly and static copies are
   identical or numerically equal in 92.4%, so the column Python keeps is
   very nearly the one R lost. Classifier: `r_join_suffix_collision`.

3. **The 999999 sentinel (8,085 rows across ~30 columns) -- R stamps a magic
   number on a cell that never held a usable number; Python nulls it.** R has
   no missing-value normalization before `as.numeric()`, so a clinician's
   "-", "NA" or free text fails to parse and R's cleaning substitutes
   `ERROR_VAL_NUMERIC`. `safe_convert_column`
   (`src/a4d/clean/converters.py`) normalizes those markers to null *before*
   conversion, deliberately. Checked exhaustively rather than sampled: every
   one of the 8,085 rows was traced back to Python's own raw stage, and **not
   one** had a clean number behind it -- 3,530 missing-value markers, 2,331
   Excel formula-error strings, 1,719 unparseable free text (e.g. "2 months"
   as an age), 505 that could not be joined back to a raw row. Python loses
   no data; the only thing R keeps is the fact of a failed parse, which
   Python records in the error log instead of in the data. This alone covered
   4,247 of `t1d_diagnosis_age`'s residual -- item 2 of this ticket's own
   question. Classifier: `r_numeric_error_sentinel`, wired from
   `get_numeric_columns()` rather than hand-listed, since the sentinel is a
   property of R's conversion step and not of any one column.

4. **`insulin_regimen` (1,348) -- a real Python bug, now fixed.** R's
   `extract_regimen` uses `sub(..., ignore.case = TRUE)`, which matches
   without case and leaves a value none of its four patterns match exactly as
   the source wrote it. Python emulated the case-insensitivity by calling
   `.str.to_lowercase()` on the column first, which permanently rewrote every
   unmatched value: "NPH" -> "nph", "Other" -> "other", "Glargine" ->
   "glargine". Fixed by moving the flag into the patterns (`(?i)`). This was
   a live data-quality regression in the production BigQuery output, not a
   comparison artefact. 1,348 -> 41.

5. **`status` (2,661) -- a config duplicate plus arbitrary dict ordering, now
   deterministic.** `reference_data/data_cleaning.yaml` lists both
   "Active - Remote" and "Active Remote" as allowed values for `status`, and
   `sanitize_str` reduces both to `activeremote`. R's
   `setNames`-list lookup returns the *first* entry; Python's dict
   comprehension kept the *last*, so 2,611 rows emitted "Active Remote" where
   R emitted "Active - Remote". Fixed to first-wins, which matches R and,
   more importantly, stops the emitted spelling depending on the order the
   config happens to list them in. Derived rather than assumed: this is the
   **only** sanitize-colliding pair in the entire config, checked by
   enumerating every `allowed_values` block. 2,661 -> 50.

**Rejected.**

- *Changing Python to take the Patient List (`.static`) copy of baseline FBG
  instead of the monthly one.* R's dropping of monthly `hba1c_baseline`
  hints its author thought the static sheet authoritative, but R never made
  that choice for FBG, and there is no evidence the static copy is truer.
  The two disagree on only 663 of ~10,000 rows, and on those the **source
  contradicts itself** -- the Patient List and the monthly sheet record
  different baselines for the same patient. Per this map's Notes that is a
  legitimate terminal answer, not something a pipeline can resolve. Left as
  an open question below rather than changed silently.
- *De-duplicating the `status` allowed-values list in
  `reference_data/data_cleaning.yaml`.* That would decide which spelling is
  canonical for production output, which is the user's call, and the config
  is shared reference data. First-wins makes the behaviour deterministic
  without making that decision. Raised for the user instead.
- *Normalizing the 999999 sentinel away inside `compare_cells`.* Follows
  ticket 26's precedent: the comparison tool documents divergence, it does
  not hide it. A classifier explains the rows; the count stays visible.
- *Forcing convergence on the remaining 16,698 rows.* They are a different
  investigation -- overwhelmingly the date-column family and its four
  distinct shapes -- and this ticket's own question pre-authorized a split.

**Evidence: executed.** Every number above was measured against the real
248-tracker `output_r`/`output_python` pair on the USB drive, not reasoned
from the code. The two source-Excel checks (500 NPT's TOTAL Insulin Units
header and values; the monthly-vs-static FBG comparison) were read directly
out of the workbooks with openpyxl. Both pipeline fixes were verified by a
full `a4d run patient --force` re-run over all 248 trackers followed by a
fresh comparison run (`output/comparison/2026-08-13T221849Z`). Full suite
639 passed / 1 skipped, `ruff check`, `ruff format --check` all pass. The
one claim not fully closed: 505 of the 8,085 sentinel rows could not be
joined back to a raw row on `(patient_id, sheet_name)` and so were counted
as untraced rather than as confirmed.

**Tense.** All statements about R describe the frozen 2025-11-14 baseline as
it exists. All statements about Python describe current behaviour *after*
this session's two fixes, except the "before" figures, which describe
behaviour as of the start of this session.

**Open question for the user.** `reference_data/data_cleaning.yaml` lists
two spellings of the same patient status. Recommendation: delete
"Active Remote" and keep "Active - Remote", which is what both pipelines now
emit and what R has always written to production. The alternative --
keeping "Active Remote" -- would change 2,611 rows of production output and
diverge from every historical R run. Not acted on: it is shared reference
data and the choice is the user's.

### Addendum (same session): the canonical-label decision, settled

The "open question for the user" above was answered in-session, and the
answer **reversed this ticket's original recommendation**. Checking the
source rather than the two pipelines showed the spellings split by tracker
generation, not at random:

| Years | Spelling | Rows | Files |
|---|---|---|---|
| 2020-2023 | `Active - Remote` | 1,421 | 30 |
| 2024-2026 | `Active Remote` | 1,354 | 28 |

Only `2024_Mahosot` mixes both, on a single row. The 2024 template redesign
introduced a `Lookup List` sheet defining the dropdown; 2022 and 2023
trackers **have no such sheet at all**, and every tracker that has one
defines `Active`, **`Active Remote`**, `Active Monitoring`, `Query`,
`Lost Follow Up` -- no hyphen. So `Active Remote` is the spelling the
current template sanctions and `Active - Remote` is the retired one. Keeping
the hyphenated form (the original recommendation, made from R's behaviour
before the source was checked) would have written a two-years-dead spelling
into production.

**Decision (the user's).** One canonical label per status, with known
aliases folded into it, and the canonical form **declared in config** rather
than implied by list order.

`reference_data/validation_rules.yaml` -- a Python-only file; R reads
`data_cleaning.yaml`, so this touches nothing R depends on -- now reads:

```yaml
status:
  allowed_values: ["Active", "Active Remote", ...]   # "Active - Remote" removed
  aliases:
    "Active Remote":          # canonical label
      - "Active - Remote"     # the retired spellings it absorbs
```

`validate_allowed_values` gained an `aliases` parameter of that shape and now
**raises** when two `allowed_values` sanitize to the same key, or when
aliases are declared for a label that is not itself an allowed value. The
first-wins ordering hack this ticket originally introduced is gone: a silent
ambiguity is now a loud config error, which is what made the original bug
invisible.

**Result, verified on a full 248-tracker re-run:** cleaned output carries one
label -- `Active Remote` 2,776, no `Active - Remote` at all. Against R's
frozen baseline this is a *deliberate* divergence of 2,611 rows (R collapses
everything onto the retired spelling via its own first-match lookup), so
cleaned-stage mismatches rise 95,490 -> 98,101 while **unclassified rows stay
at 16,698** -- the new rows are explained, not added to the backlog. The new
`python_canonical_label` classifier reads the alias map out of the same YAML
that produced the values, and its column wiring is derived from that config
too, so a future alias needs no code edit. The 50 residual `status` rows are
genuinely different statuses (e.g. R `Discontinued` vs Python `Active`) and
belong to [ticket 37](37-triage-patient-cleaned-residual-2.md).

**Rejected:** reordering `allowed_values` so the canonical spelling sits
first. It gets the right answer today but encodes the decision as list
position -- insert order by another name -- which is exactly the fragility
that produced the original defect.
