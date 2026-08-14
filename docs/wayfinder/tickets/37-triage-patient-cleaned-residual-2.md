---
id: 37
title: Triage the residual patient cleaned-stage mismatches (round 2)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-14
claimed_at: 2026-08-14
resolution: decided
evidence: executed
closed_by: null
spawned_by: 29
---

## Premise

Rests on [Triage the residual patient cleaned-stage column
mismatches](29-triage-patient-cleaned-residual.md), closed: that ticket
root-caused the two priority columns its own question named and, along the
way, the whole 999999-sentinel family. Two real Python bugs were found and
fixed (`extract_regimen` lowercasing every value it did not match;
`validate_allowed_values` picking the last of two colliding config
spellings), and three classifiers were added
(`r_insulin_dedup_drop`, `r_join_suffix_collision`,
`r_numeric_error_sentinel`). Cleaned-stage mismatches fell 99,408 ->
95,490 and unclassified rows 55,670 -> 16,698 (-70%), verified against a
fresh 248-tracker pipeline re-run and comparison.

It split the rest off rather than force convergence, per its own
pre-authorization.

## Question

Triage the 16,698 remaining unclassified cleaned-stage mismatches. Re-run
`just compare-outputs` first -- ticket 29's run
(`output/comparison/2026-08-13T221849Z`) is the baseline. Current shape,
largest first:

- **`blood_pressure_updated` (4,504)** -- 4,442 of these are Python-null
  where R holds a value, plus 48 where Python holds the future-date
  sentinel against a Thai Buddhist-Era year in R (2568/2569). The
  Buddhist-Era half is the *inverse* direction of the existing
  `buddhist_era_typo` classifier, which was written for the raw stage
  (R sentinels, Python passes through); at the cleaned stage Python's own
  future-date guard sentinels it and R carries the bad year through. The
  py-null majority is not characterized at all and is the real question.
- **The date-column family: `hospitalisation_date` (2,149),
  `hba1c_updated_date` (1,809), `fbg_updated_date` (1,800),
  `t1d_diagnosis_date` (1,082), `last_clinic_visit_date` (193)** -- each
  mixes four shapes in different proportions: Python-null vs R-value,
  Python-sentinel vs R-date, R-sentinel vs Python-null, and both-real.
  `fbg_updated_date` also shows a 1900-01-03 vs 1900-01-04 pair, which
  looks like the Excel 1900-leap-year serial bug ticket 24 already handled
  once in `STRAY_DATE_CLASSIFIERS` -- worth checking whether that
  classifier's logic applies here.
- **`insulin_type` (1,265)** -- 1,252 are R-null where Python has a real
  value ("Analog Insulin"). `insulin_type` is derived by the same
  `_derive_insulin_fields` step whose sibling `insulin_subtype` is already
  explained by `r_validator_rejects_multivalue`; check first whether this is
  the same cause with a different symptom.
- **`t1d_diagnosis_age`'s remaining 560 and `recruitment_date`'s remaining
  502** -- what is left of each after ticket 28's and ticket 29's causes
  were removed.
- **A tail of ~50 smaller columns**, including `observations` (327) and the
  blood-pressure value pair (`blood_pressure_dias_mmhg` 303,
  `blood_pressure_sys_mmhg` 240), none sampled.

Same method: look for systematic shapes, fall back to the real source Excel
trackers as the arbiter (mount at `/Volumes/USB SanDisk 3.2Gen1 Media/a4d/`),
add named causes to the `PATIENT_*_CLASSIFIERS` registries in
`src/a4d/migration/compare.py` (`scripts/compare_outputs.py`'s
`CLASSIFIERS_BY_COLUMN` wires them to columns) -- or fix a real Python bug
directly, as ticket 29 did twice, when one turns up.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: it is not
enough to explain a difference and name a cause. Each one must also carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Noting
"Python has A where R has B" and adding a classifier is not a decision in
favour of A. Where Python turns out to be wrong or to be losing information
the source file carried, fix the pipeline rather than labelling the symptom.
A cause genuinely undecidable on available evidence is recorded as an open
question, not closed with a label; where the evidence shows the source file
itself is corrupt, "the source is wrong, this tracker needs human
inspection" is a legitimate final conclusion.

## Resolution (session-2026-08-14)

**Decision.** Four of the five named leads are resolved, three of them by
fixing a real Python bug rather than by naming a cause. Unclassified
cleaned-stage mismatches fell **16,698 -> 8,259 (-51%)**, total mismatches
98,101 -> 93,997. The date-column family did not converge and is split into
[ticket 38](38-triage-patient-cleaned-date-family.md), per this ticket's own
method note.

**Pipeline bugs found and fixed** (all four are data-loss or
non-determinism, none was a labelling job):

1. `merge_headers` (`src/a4d/extract/patient.py`) produced the unmappable
   header `Updated 2022 Date` for every 2022 tracker, because that template
   writes `Updated 2022` in the upper header row instead of repeating the
   subject column's name. R carries an explicit fixup for exactly this
   (`script1_helper_read_patient_data.R`, lines 47-61). Python now treats a
   whole-cell `Updated <year>` as a continuation of the column to its left,
   which reproduces R's result without hardcoding either the year or the two
   affected column names. Recovered **4,442 `blood_pressure_updated` and
   2,723 `edu_occ_updated` values**; `blood_pressure_updated` mismatches
   4,504 -> 62.
2. `_apply_type_conversions` (`src/a4d/clean/patient.py`) stripped a trailing
   time component by splitting on the first space and keeping the first
   token, which destroyed genuine space-separated dates: `"Jun 2006"` became
   `"Jun"`, which dateutil completed from **today's date**, producing a
   future date that `_validate_dates` then replaced with the 9999-09-09
   sentinel. Two defects in one: real diagnosis dates lost, and output that
   changes depending on the day the pipeline runs. Now matches the trailing
   time pattern itself.
3. `parse_date_flexible`'s month-name truncation deleted only the *fourth*
   letter (`re.sub(r"([a-zA-Z]{3})[a-zA-Z]", ...)`), so `"March"` became
   `"Marh"` and `"January"` became `"Janary"` -- unparseable, and sentinelled.
   Every full month name in the trackers was affected, including the
   function's own docstring examples, which never worked. Now anchored on a
   month-name alternation.
4. `parse_date_flexible`'s month-year branch only accepted a 2-digit year, so
   `"Jun 2006"` fell through to dateutil's today-based day fill even once (2)
   was fixed. Extended to 4-digit years, resolving to the first of the month
   -- matching both R and Python's own 2-digit behaviour.

Fixing (2) removed the trailing-free-text truncation it had been doing by
accident (`"16-Nov-2019 due to DKA"`), so `parse_date_flexible` gained an
explicit longest-parseable-prefix fallback, tried only after the whole string
fails, and skipping a purely alphabetic prefix (a bare month name is what
made the old behaviour depend on the run date).

Measured on the real 254-tracker pair: date-column mismatches fell 2,344
(`fbg_updated_date` -761, `hba1c_updated_date` -734, `recruitment_date` -422,
`t1d_diagnosis_date` -419).

**Classifiers added or extended**, each source-verified:

- `r_extraction_gap` extended to `blood_pressure_updated` and
  `edu_occ_updated` (2,785 rows), covering two distinct R mechanisms
  documented in its docstring: R's own 2022 header fixup is defeated by a
  *leading space* in the source cell (` Updated \n2022`), so R's merged name
  sanitizes to the junk column `xlevelofeducationoroccupationdate` that no
  synonym matches -- confirmed in R's own raw parquet; and R reads nothing at
  all from the 2026 template's new `Annual` sheet, verified against
  `2026_YGH T1D Tracker_June_26`, `Annual!G/H/I` for MM_YG101
  (2026-02-05, 100, 60) where R's whole-file count is 0 non-null. The
  registry was renamed `PATIENT_RECRUITMENT_DATE_CLASSIFIERS` ->
  `PATIENT_R_EXTRACTION_GAP_CLASSIFIERS`, since it now serves three columns.
- `r_ifelse_na_propagation` (new, `insulin_type`, 1,252 rows): R's
  `ifelse(pre_mixed == "Y" | short == "Y" | intermediate == "Y", ...)`
  evaluates `FALSE | FALSE | NA` as NA under R's three-valued logic, so a row
  whose human-insulin columns are blank but whose *analog* columns plainly
  read "Y" loses its type entirely. Verified both pipelines hold the same
  five input values (2026 Baguio General, May26, PH_BG001 and PH_BG004).
  Python is the correct side; not the same cause as
  `r_validator_rejects_multivalue` on the sibling `insulin_subtype`.
- `buddhist_era_typo` made symmetric: at the cleaned stage the direction
  reverses on `blood_pressure_updated` (R carries the Buddhist-Era year
  through, Python's future-date guard sentinels it). Same typo, same verdict
  -- the sentinelling side is the one that recognized an unusable year.
- `python_future_date_sentinel` reused for `edu_occ_updated`'s reverse
  direction (17 rows); its docstring now names patient's `_validate_dates`
  alongside product's `_validate_entry_dates`.

**Rejected.** Writing a `blood_pressure_updated` classifier for the 4,442
Python-null rows: the shape said "Python has nothing" and the source said
otherwise (2022 Kantha Bopha, `Jan'22` col 27, KH_KB022 = 2022-01-19
alongside a BP of 110/60), so labelling it would have cemented an extraction
bug as explained -- ticket 27's precedent exactly. Distinguishing
`edu_occ_updated`'s two R mechanisms as separate cause names: `classify()`
sees only the (r_value, py_value) pair, never the file, so it cannot tell a
2022 tracker from a 2026 one; both are documented under one name instead,
following `_is_r_value_missing`'s precedent.

**Found, deliberately not fixed.** 13 `insulin_type` rows where R and Python
hold the *same* two rows in a different order, because the patient row key
(`patient_id` + `sheet_name`) is duplicated for that patient in that sheet.
That is a comparison-tool alignment issue, not a pipeline divergence, and the
same shape [ticket 31](31-triage-patient-raw-residual-2.md) already flagged
for the raw stage -- a classifier here would be a false explanation. Left
unclassified deliberately, and noted on ticket 38.

**Evidence.** Executed. Every claim above rests on a run or a query against
the real drive data, not on reading: two full `a4d run patient --force`
re-runs over the whole tracker set, four `just compare-outputs` runs
(`output/comparison/2026-08-14T195310Z` immediately before the data refresh,
`2026-08-14T200342Z` after), direct openpyxl reads of the named source
workbooks, and direct queries against R's own raw and cleaned parquets. Full
suite 655 passed / 1 skipped, `ruff check`, `ruff format --check`, `ty check
src/` all pass.

**Tense.** Every number above describes current behaviour after this
session's changes, except the "before" figures, which describe the state at
ticket 29's close.

## Addendum (same session, after closure): tracker set refreshed to 254

At the user's direction, after this ticket's work was verified: production
trackers were re-downloaded (`a4d download trackers`, 47 new files) after the
data analyst renamed every `06 ...` file to a `2026_...` form and added new
clinics. Three consequences were handled so the R comparison survives:

- The 41 stale `06 ...` local copies (absent from GCS) were **moved**, not
  deleted, to `/Volumes/.../a4d/stale_06_trackers_2026-08-14/`. Left in place
  they would have been processed alongside their renamed twins, double-counting
  every 2026 patient. Local tracker count now matches GCS exactly (254).
- The comparison pairs R and Python outputs **by file name**, so the rename
  would have silently dropped ~41 files out of the cell-by-cell comparison
  (Python-only on one side, R-only on the other). The frozen R output's 322
  per-tracker files were renamed to the corrected names instead, the mapping
  derived from the clinic folder (`clinic_id` is the parent folder name, so
  the pairing is authoritative, not guessed) and verified 1:1 with zero
  collisions. The map is saved at
  `/Volumes/.../a4d/output_r_rename_map_2026-08-14.json`, so the rename is
  reversible. Result: **0 R-only files** on every stage.
- Renaming the files left R's parquets holding the *old* stem in their own
  `file_name` column -- the only column carrying it -- which produced 33k
  phantom mismatches by construction. Rewritten in place across 160 R
  parquets / 40,701 rows, restoring the counts exactly (patient cleaned
  unclassified 15,643 -> 8,259).

R was **not** re-run, per the user's decision: the 9-25 genuinely new
trackers per stage have no R counterpart and show as Python-only, which is
accepted. Post-refresh state, all four stages: patient cleaned 93,997
mismatches / 8,259 unclassified; patient raw 27,921 / 14,844; product cleaned
22,718 / 20; product raw 118 / 0.
