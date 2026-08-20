---
id: 47
title: Four trackers where cleaning merges several patients into one patient ID
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-20b
claimed_at: 2026-08-20T12:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 45
---

## Premise

Rests on [Give the patient comparison an ordinal row key](45-patient-row-alignment-duplicate-keys.md),
closed, which established that `patient_id` + `sheet_name` is patient's real
identity key and made duplicate-key groups visible per file and per stage. Two
of the five cleaned-stage duplicate groups it found have no raw-stage
counterpart, which is how this surfaced: the duplication is created *by
cleaning*, not read from the source.

Measured directly against the real 254-tracker output on the USB drive
(executed, not inferred):

- `2023_NPH A4D Tracker`, sheet `Sep23`: four distinct raw identities --
  `KH_NPH026`, `KH_NPH027`, `KH_NPH028`, `KH_NPH029` -- arrive at the cleaned
  stage as a single `KH_NPH02` with four rows. Every other patient in that file
  is keyed `KH_NP0xx`, so the four carry an odd prefix in the source.
- Across all 254 trackers, **4 files lose 9 identities** between raw and
  cleaned (distinct `patient_id` count drops). Row counts are preserved --
  nothing is dropped or invented, the identities are merged.

**R does exactly the same thing on the same file**, so this is not a Python
regression and not an R/Python divergence. That is why no comparison-based
ticket could have found it: both sides agree, and agreement is what the
comparison tool is built to stay quiet about. It also means this ticket does
not need R alive to answer -- it is a question about the Python pipeline and
the source workbooks.

`clean/patient.py`'s `_apply_preprocessing` normalizes `patient_id` by
converting hyphens to underscores and keeping `^([A-Z]+_[^_]+)` -- documented
as removing a transfer-clinic suffix (`MY_SM003_SB` -> `MY_SM003`). Ticket 45
**read** this and could not see how it produces `KH_NPH026` -> `KH_NPH02`,
since that value has only one underscore. Treat the mechanism as unlocated, not
as diagnosed.

## Question

Find out what merges these identities, and decide what the pipeline should do.

1. **Locate the mechanism.** Not the `patient_id` regex on its face -- read the
   actual value at each step (raw parquet, preprocessing, the Patient List
   join) for one of the four `2023_NPH` rows rather than reasoning from the
   code. The Patient List join is the prime suspect, since the cleaned
   identity may be coming from the Patient List rather than the monthly sheet.
2. **Decide whether the source is wrong or the pipeline is.** Open
   `2023_NPH A4D Tracker.xlsx` and see what the `Sep23` sheet and the Patient
   List actually record for these four patients. If the workbook itself
   conflates them, that is a finding for [ticket
   40](40-source-defect-findings-report.md), not a pipeline fix. If the
   pipeline is collapsing identities the workbook keeps distinct, that is
   patient data being attributed to the wrong person, and the pipeline gets
   fixed.
3. **Name the other three files.** Ticket 45 counted them (4 files, 9
   identities) without listing them; derive the list rather than assuming they
   share `2023_NPH`'s shape.

## Standing bar

Per the map's **triage means deciding, not labelling**: a named cause is not
enough -- say explicitly whether the merged identity is correct, with what was
read in the source workbook. This one carries more than a mismatch count: if
cleaning is merging distinct patients, the production `patient_data_*` tables
attribute one patient's monthly records to another.

## Resolution

**Decision.** `fix_patient_id` (`src/a4d/clean/validators.py`) no longer
truncates. An ID that fails the `XX_YY###` format is now **recovered** against
the well-formed IDs the same tracker carries elsewhere -- accepted only at edit
distance 1 and only when exactly one candidate fits -- and **sentinelled to
`Undefined`** when no unambiguous candidate exists. Every malformed ID is
reported to the `ErrorCollector` whether recovered or sentinelled, since either
way the source workbook needs correcting (user's explicit instruction).

The user chose this shape: "C as first rule and B as fall back" -- recover
where the tracker's own Patient List settles the intended identity, sentinel
otherwise, because "otherwise we publish patient IDs that are not in any
tracker."

**1. The mechanism, located by execution.** Not the `patient_id` regex in
`_apply_preprocessing` (step 2), which the ticket's premise correctly refused
to accept as diagnosed. Bisecting all eleven cleaning steps over the real
`Sep23` slice put the change in `validate_all_columns` (step 7), which calls
`fix_patient_id` last. Its rule: non-conforming and longer than 8 characters
-> truncate to the first 8; 8 or shorter -> `Undefined`. `KH_NPH026` is 9
characters, so all four collapsed onto `KH_NPH02`.

This was a faithful port. R's `fix_id`
(`r-archive/R/script2_helper_patient_data_fix.R:681-728`) has the identical
asymmetry -- `str_sub(id, 1, 8)` for long, `ERROR_VAL_CHARACTER` for short.
The premise's hypothesis of a hyphenated source spelling (`KH_NPH02-6`) is
**dead**: the raw parquet holds `KH_NPH026` with no hyphen.

**2. The source is wrong, and the pipeline made it worse.** Read directly from
`Cambodia/NPH/2023_NPH A4D Tracker.xlsx`, rows 128-131 of each sheet: the
`Patient List`, `Oct23`, `Nov23` and `Dec23` all write `KH_NP026`-`KH_NP029`;
only `Sep23` writes `KH_NPH026`-`KH_NPH029`. One sheet, one stray `H`, at the
patients' enrolment month.

So the workbook is defective -- a finding for [ticket
40](40-source-defect-findings-report.md). But truncation did not merely fail to
repair it: it manufactured `KH_NPH02`, an identifier present in no source
workbook anywhere, and filed four different people's September records under
it. The function was also self-inconsistent -- a 7-character bad ID was
honestly sentinelled while a 9-character bad ID was silently reshaped into
something that looks real.

**3. The other three files are three different mechanisms, and two are the
pipeline working correctly.** Ticket 45's count of "4 files, 9 identities" is
right; its implied uniform shape is not.

| File | What happens | Verdict |
|---|---|---|
| `2023_NPH A4D Tracker` | 4 IDs truncate onto `KH_NPH02` (-3) | **Wrong** -- source typo amplified into a false merge |
| `2021_Mahosot Hospital A4D Tracker_DC` | `LA-MH056/057/058` (Jun-Nov) merge into `LA_MH056/057/058` (Dec) (-3) | **Correct** -- same patients, hyphen vs underscore across months |
| `2026_Surat Thani Hospital A4D Tracker_Jun_26` | `TH-ST029` merges into `TH_ST029` (-1) | **Correct** -- same patient, two spellings |
| `2026_NOGH T1D Tracker_June_26` | `MM_NO97`, `MM_NO98`, `MM_NO99` (7 chars) all -> `Undefined` (-2) | **Source defect** -- 18 rows of 3 distinct patients share one sentinel |

**Recovery is deliberately narrow, and the NOGH case is why.** `MM_NO97/98/99`
look like a missing leading zero, but that workbook's **own Patient List**
writes `MM_NO97/98/99` too, and it has `MM_NO090`-`MM_NO096` with no
`MM_NO097`. Nothing in the tracker licenses inventing one, so they stay
`Undefined` -- unchanged by this fix, and reported. Same for
`2026_YGH T1D Tracker_June_26`'s `MM_NO55_MW_YG` (3 rows, one identity, no
merge).

**Rejected.**
- *Change nothing / stay bit-faithful to R.* Rejected by the user: it keeps
  publishing an identity no tracker contains.
- *Sentinel only, never recover (option B alone).* Rejected as the primary
  rule, kept as the fallback. It removes the misattribution but throws away
  four recoverable rows when the tracker itself says what was meant.
- *Recover by fuzzy-matching the Patient List with a looser rule.* Not
  attempted. Edit distance 1 plus a uniqueness requirement is what makes the
  recovery a reading rather than a guess; anything looser risks attaching a
  mistyped ID to a different real patient, which is the exact failure this
  ticket exists to remove.
- *Fix the extraction-side Patient List join in the same session.* Split out --
  see the spawned ticket below.

**Evidence: executed.** The mechanism was found by bisecting the cleaning
steps over real data, not by reading the code (reading is what left the premise
with the wrong suspect). The source verdict was read from the workbook's own
cells. The blast radius was measured by re-cleaning **all 254 raw parquets** on
the USB drive with the new code and diffing every file's `patient_id`
distribution against the existing cleaned output: exactly one file changes.

- `2023_NPH A4D Tracker`: `KH_NPH02` (4 rows) disappears; `KH_NP026`,
  `KH_NP027`, `KH_NP028`, `KH_NP029` each go 3 rows -> 4.
- Every other tracker is byte-identical, including NOGH, YGH, Mahosot DC and
  Surat Thani.
- Corpus-wide, the cleaned output now contains **zero** patient IDs that fail
  the `XX_YY###` format (previously one: `KH_NPH02`).
- The recovered rows attach to the right people: `KH_NP026`'s September row
  joins a patient whose own `t1d_diagnosis_date` is 2023-09-04.

Full suite 865 passed / 1 skipped, `ruff check`, `ruff format --check` and
`ty check src/` all clean. Six new tests in
`tests/test_clean/test_validators.py`; three pre-existing tests that asserted
R's truncation were rewritten to the decided behaviour rather than deleted.

**Tense.** Everything above describes current behaviour on this branch after
the fix, except the R descriptions, which are of `r-archive/` as frozen.

## Spawned

- **The recovered rows have no demographics, because extraction joins the
  Patient List on the *unfixed* ID.** `KH_NP026`'s September row now carries
  the right identity but null `dob`, `sex`, `province` and
  `t1d_diagnosis_date`, where its October-December rows have all four. The
  Patient List join happens in `extract/patient.py` (~line 1107), long before
  `fix_patient_id` runs in cleaning, so a misspelled monthly ID silently misses
  its own demographics. This is a second, independent defect of the same source
  typo, and its blast radius is not the 4 NPH rows alone -- it plausibly also
  covers the hyphen-spelled Mahosot and Surat Thani rows, whose Patient List
  entries use underscores. Split out rather than fixed here: changing the join
  key changes matching for every tracker, which is a different measurement.

## Reported to ticket 40

- `2023_NPH A4D Tracker`, `Sep23`, rows 128-131: `KH_NPH026`-`KH_NPH029`
  should be `KH_NP026`-`KH_NP029` (stray `H`; the same workbook's Patient List
  and its Oct/Nov/Dec sheets spell them correctly).
- `2026_NOGH T1D Tracker_June_26`: `MM_NO97`, `MM_NO98`, `MM_NO99` are
  7-character IDs where the template wants 8, in the Patient List and every
  month sheet. Three distinct patients, currently all published as
  `Undefined` (18 rows). Cannot be repaired in the pipeline -- the workbook
  has to say what was meant.
- `2026_YGH T1D Tracker_June_26`: `MM_NO55_MW_YG` reduces to `MM_NO55`, again
  7 characters. One patient, 3 rows, published as `Undefined`.
- `2021_Mahosot Hospital A4D Tracker_DC`: `LA-MH056/057/058` in Jun-Nov vs
  `LA_MH056/057/058` in Dec -- the same patients spelled two ways within one
  workbook. The pipeline merges them correctly; the workbook should still be
  made consistent.
- `2026_Surat Thani Hospital A4D Tracker_Jun_26`: `TH-ST029` and `TH_ST029`
  both appear in `May26`, so that patient has two rows for one month after
  normalization -- likely a duplicated entry in the source.

## Addendum (same session, after closure): the comparison was re-run

The resolution above was recorded before the R/Python comparison had been run
against the changed output. The user asked for it immediately after, so it is
recorded here rather than left as an open thread.

The patient arm was regenerated with `a4d run patient` against the real
254-tracker set on the USB drive (85,300 monthly rows), replacing
`output_python/`'s patient stages; product was untouched and its report
confirms "no change from the previous run". `just compare-outputs` was then run
against the frozen `output_r/`.

**The divergence this fix creates is row-key non-overlap, not cell mismatches**
-- which is worth stating plainly, because a future session scanning the
`cell_mismatches` sheet will not find it there. Patient's row-alignment key is
`patient_id` + `sheet_name`, so R's four `KH_NPH02` rows and Python's four
recovered `KH_NP026`-`KH_NP029` `Sep23` rows no longer pair with each other:

- Row-key divergence, whole patient cleaned stage: **6 files / 121 R-unmatched
  / 15 Py-unmatched -> 7 files / 125 / 19**. The entire delta is
  `2023_NPH A4D Tracker` gaining 4 R-unmatched and 4 Py-unmatched. No other
  file moved.
- Cell mismatches, whole patient cleaned stage: **114,373 -> 114,371**. Both
  removed cells are FBG (`fbg_updated_mg|python_glucose_unit_corrected` 5,341
  -> 5,340 and `fbg_updated_mmol|unclassified` 2,936 -> 2,935), from two of
  those same four rows, which previously paired with R and contributed a
  mismatch each.
- **No new `unclassified` cells**, and the per-column table shows no other
  column moving at all.
- Patient raw stage: **zero delta**, as expected -- the fix is in cleaning.

No cause classifier was added. The cause registry classifies *cell* mismatches
and this divergence never reaches a cell comparison, so a classifier could not
fire on it; the standing entry in the map's Decisions-so-far is where it is
documented instead. This is the same shape as the ticket-42 unit swap, which
the map's fog already records as a finding no per-cell classifier can see.

**Tense:** these are current measured numbers on this branch, against
`output_r/` as frozen.
