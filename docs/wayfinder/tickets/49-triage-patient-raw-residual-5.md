---
id: 49
title: Triage the residual patient raw-stage column mismatches (round 5)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-18
claimed_at: 2026-08-18T10:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 46
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches (round
4)](46-triage-patient-raw-residual-4.md), closed, which took patient raw-stage
unclassified from **601 to 278** by settling four causes: a number typed into a
date-formatted cell (pipeline fix, 38 rows), R's dropped rich-text space
(classifier, 89), Python's trimming of merged sub-values (classifier, 2), and
`insulin_regimen`'s blank header in `2021_Kantha Bopha` (classifier, 194).

**Updated 2026-08-17, after [ticket
48](48-putrajaya-screening-columns-lost.md) closed.** The residual is now
**229**, measured on baseline run `output/comparison/2026-08-17T222225Z`, which
is the run to triage against. Every count measured before it -- including the
278 below and every per-shape figure in the Question -- is historical.

Ticket 48 removed **49** of the 278, not the ~25 first estimated: its
merged-header fix took `complication_screening_results` 11 -> 0 and
`complication_screening_date` 31 -> 0, and moved 7 `observations` rows from
unclassified onto the existing `r_na_unite_padding` classifier. Three shapes
listed below are therefore already gone -- see the Question's notes.

Rests also on the map's standing scoping rule that the current tracker template
is the golden rule, and on the standing bar that a classifier records
understanding, never a verdict by itself.

## Question

Triage the 229. The shapes below were counted against the *old* 278-row
baseline; three of them are already resolved by ticket 48 and are struck
through in place rather than deleted, so the arithmetic stays checkable.
Re-measure the rest against `output/comparison/2026-08-17T222225Z` before
working them -- do not trust these numbers.

- **R null, Python has a value (~125 rows, ~12 columns)**:
  `last_clinic_visit_date` (40, one file), `fbg_updated_date` (25),
  `blood_pressure_sys_mmhg`/`blood_pressure_dias_mmhg` (13 each), `edu_occ`
  (12), `last_remote_followup_date` (4), `hospitalisation_cause` (3),
  `other_issues` (2), `status` (1). Shape-identical to `r_extraction_gap`, but
  ticket 31's refusal applies: verify per column against the source before
  wiring, or the classifier labels without deciding.
- **A real date typed into a numeric column, or the reverse (51)**:
  ~~`complication_screening_date` (31)~~ -- **resolved by ticket 48**: it was
  exactly the predicted gap, a raw-only date column `get_date_columns()` cannot
  derive, now appended to `PATIENT_RAW_DATE_NORMALIZE_COLS`. 31 -> 0.
  `t1d_diagnosis_age` (16, source defect -- see [ticket
  40](40-source-defect-findings-report.md)), `blood_pressure_mmhg` (3),
  `testing_frequency` (1).
- **`t1d_diagnosis_date` (23, two files)**: R 41837 vs Python 41821 in
  `2017_Yangon` -- two different real dates 16 days apart, so neither side is
  null and neither is obviously right. Unexplained.
- **Booleans (25)**: R `FALSE` vs Python `False` on `clinic_visit` and
  `remote_followup`, one and two files. A representation difference; decide
  normalization vs classifier.
- **R null vs Python empty string (25)**: `insulin_injections` (22),
  `hba1c_updated` (3). Python emitting `""` where the source cell is blank
  looks like a Python cleanliness defect worth fixing rather than classifying.
- **`dm_complications` (15, two files)**: `Kidney \nDamage` on both sides,
  visually identical in the report. Inspect the bytes before assuming a cause.
- **`observations` (8 -> 1)**: mostly **resolved by ticket 48** -- 7 of the 8
  were Putrajaya rows where Python had a screening selection misfiled into
  `observations`; with Python now correctly null they match the existing
  `r_na_unite_padding` classifier. **1 row remains**: R's `... January ,NA`
  against Python's `... January`, where the classifier still does not fire (the
  trailing space before the comma is the likely reason).
- **`complication_screening` (2)**: Python holds two selections where R holds
  one. Ticket 48 established that both pipelines keep only the *first*
  selection of a multi-select block, so re-measure this before assuming it
  still says what it says.
- **`hospitalisation_date` (5)**: Python's raw value is `2958352`, the Excel
  serial for 9999-12-31 -- the date sentinel appearing at the *raw* stage,
  which raw is not supposed to carry.

Split further rather than leaving this open-ended if it does not converge.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.

## Resolution

**Decision.** Patient raw-stage unclassified goes **229 -> 84** (63%), settled
by four causes: two comparison-tool defects fixed, and two R limitations
root-caused to a named mechanism and classified. Python is right in every one
of the four; no pipeline change was needed, which is itself the finding --
unlike ticket 46 and ticket 48, this round's residual held no Python defect.
The remaining 84 did not converge and are split into [ticket
50](50-triage-patient-raw-residual-6.md).

**1. The whitespace target list was derived from the wrong schema (40 rows).**
`PATIENT_WHITESPACE_NORMALIZE_COLS` resolved through `get_string_columns()`,
i.e. the *cleaned* patient schema, but the raw stage stores every value as
text. That list cannot see a raw-only column (`dm_complications`, 15 rows, no
cleaned equivalent) and excludes as non-string the columns the cleaned schema
types `Float64` (`insulin_injections` 22, `hba1c_updated` 3), so readxl's
`trim_ws=TRUE` and its `\r\n` line endings kept surfacing on exactly those
three. This is the identical defect ticket 43 fixed for the *numeric* list,
never applied to the whitespace one. Added `whitespace_normalize_targets()`
(`src/a4d/migration/compare.py`) -- every string column, minus `__` join
helpers -- reusing the existing `ALL_RAW_COLUMNS` sentinel, wired to the
Patient (raw) stage only. The cleaned stage keeps the schema-derived list,
where the dtypes are real.

`dm_complications` is why this went unfound for five rounds: the Excel report
shows both sides as byte-identical `Kidney \nDamage`, because DuckDB's xlsx
reader normalizes `\r\n` away on read. Unzipping the workbook and dumping
`xl/worksheets/sheet10.xml` shows R's `Kidney \r\nDamage` against Python's
`Kidney \nDamage`. **A shape that looks identical in the report is not
evidence the values are equal** -- inspect the bytes at the source.

**2. R and Python spell an Excel boolean differently (20 rows).** readxl reads
a logical and R writes `FALSE`; openpyxl reads a Python `bool` and Python
writes `False`, on `clinic_visit` and `remote_followup`. Only a genuine Excel
boolean produces both spellings at once, so neither side is wrong. Checked
whether it reaches cleaned output: it does not -- **zero** mismatches on either
column at the cleaned stage, because cleaning canonicalizes both. That makes it
a raw-stage representation artifact, handled like `\r\n` and the date serials
rather than labelled: `normalize_boolean_literal_column()` folds only the exact
literals, so free text containing "false" is untouched.

**3. R's header sanitizer keeps non-Latin script (44 rows).** `2022_Mukdahan`
appends Thai translations to two headers -- `Mar22!F44` is
`'Last Clinic \nVisit\nไปโรงพยาบาล'`, `G44` is `'Last Remote \nFollow
Up\nสายเข้า'`. R's `sanitize_str` strips `[^[:alnum:]]`, whose character class
is Unicode-aware, so the Thai survives: the header sanitizes to
`lastclinicvisitไปโรงพยาบาล`, `harmonize_patient_data_columns`' `match()` is
exact equality, no synonym matches, and R drops the column -- every row null.
Python's `sanitize_str` strips to `[^a-z0-9]`, reduces the same header to
`lastclinicvisit`, and matches. Executed both implementations on the real
header string rather than reading the two regexes; verified against the source
(`Mar22!F46` = 2022-02-17 = Python's serial 44609). Python recovers 44 real
dates R discards. New classifier `r_non_latin_header_miss`
(`PATIENT_NON_LATIN_HEADER_CLASSIFIERS`), registered for
`last_clinic_visit_date` and `last_remote_followup_date`.

Incidental, not fixed: Python's `sanitize_str` docstring claims it "matches the
R implementation". It does not, and here the divergence favours Python.

**4. The 2026 Annual sheet reaches five more columns (41 rows).** Ticket 37
already verified that the 2026 template moved a block to a new `Annual` sheet
that R reads no values from; `r_extraction_gap` simply was not registered for
`blood_pressure_sys_mmhg`, `blood_pressure_dias_mmhg`, `edu_occ`,
`other_issues`, `status`. Verified per column against the source rather than
wired on shape (ticket 31's refusal): `2026 ISDFI, Annual!E32/H32/I32/AD32` for
`PH_IS022` reads `"college graduate"`, `80`, `50`, `"for cataract surgery"` --
exactly Python's four values. Confirmed the monthly sheet's patient header row
(`May26!162`) carries no blood-pressure or education column at all, so the
Annual sheet is the only source, and that both pipelines *do* read the Annual
sheet -- R's gap is column-level, not sheet-level.

**Because.** Two of the four were the comparison tool mis-measuring, not the
pipeline diverging, and the map's precedent is unambiguous that a representation
artifact gets normalized rather than classified (tickets 20, 22, 43). The other
two are R limitations with a mechanism traced to R's own source, which is the
bar ticket 31 set when it refused to wire `r_extraction_gap` on shape alone.

**Rejected.**
- *Classifying the whitespace and boolean shapes instead of normalizing.* A
  classifier would have recorded 60 rows as "understood" while leaving the tool
  mis-measuring every future run, and would have hidden the `dm_complications`
  `\r\n` from every later round exactly as it had been hidden for five.
- *Wiring `r_extraction_gap` across all ~125 R-null rows at once.* Shape-
  identical, and it would have closed the ticket in one line -- but ticket 49
  found the R-null rows have **at least three** distinct mechanisms (Mukdahan's
  header, 2026's Annual sheet, and a still-unexplained `2019_Preah Kossamak`
  which has no non-Latin header divergence at all). A single classifier would
  have cemented all three as one understood cause.
- *Extending `normalize_whitespace_column` to interior whitespace.* Ticket 46
  rejected this and nothing here reopens it; widening the column *scope* is a
  different change from widening what it strips.
- *Chasing the remaining 84 this session.* Splitting is the map's own rule and
  each remaining shape needs its own source-workbook check.

**Evidence.** `executed` throughout. Both comparison runs were real: 229 -> 169
after the two normalizations, 169 -> 84 after the two classifiers, against the
full 248-tracker drive data (`output/comparison/2026-08-18T134503Z` and
`2026-08-18T135258Z`). Source-Excel claims were read out of the real workbooks
on the drive; the R/Python sanitizer divergence was produced by running both
implementations, not by reading them. Full suite 752 passed, 1 skipped (+10
new tests; the drive being mounted also un-skipped 65 drive-dependent tests
that had been skipped earlier in the session), ruff and `ty check src/` clean. The one judgement call is that
`2026 Surat Thani` and `2026 YGH`'s `edu_occ` rows share ISDFI's mechanism:
verified same template and same shape, mechanism traced directly on ISDFI only.

**Tense.** Every count above is current behaviour, measured after the change.
