---
id: 38
title: Triage the patient cleaned-stage date-column family (round 3)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-14b
claimed_at: 2026-08-14T21:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 37
---

## Premise

Rests on [Triage the residual patient cleaned-stage mismatches (round
2)](37-triage-patient-cleaned-residual-2.md), closed: four real Python bugs
were fixed (the 2022 `Updated 2022` header, the first-space date split, the
broken month-name truncation, and the 2-digit-only month-year branch) and
three causes named (`r_extraction_gap` extended to two more columns,
`r_ifelse_na_propagation`, `buddhist_era_typo` made symmetric). Unclassified
cleaned-stage mismatches fell 16,698 -> 8,259.

It also rests on [Triage the patient cleaned-stage column
mismatches](28-triage-patient-cleaned.md) and [its
residual](29-triage-patient-cleaned-residual.md), which between them
established that R's 999999 sentinel is a correct Python representation
choice and that R's own extraction gaps -- not Python defects -- explain the
largest cleaned-stage columns.

Two of ticket 37's own fixes matter to this ticket's framing: the date parser
now resolves month-year strings to the first of the month deterministically,
and recovers a date followed by a free-text clause via a longest-parseable-
prefix fallback. Several date columns' remaining mismatches are what survived
those fixes, so they are **not** the same population ticket 37 opened with.

Also rests on the tracker set having been refreshed to 254 files with the R
baseline renamed to match (ticket 37's addendum): the current baseline is
`output/comparison/2026-08-14T200342Z`, not any earlier run.

## Question

Triage the 8,259 remaining unclassified cleaned-stage mismatches. Re-run
`just compare-outputs` first. Current shape, largest first, with the value
shapes already measured (`r_sent`/`py_sent` = the 9999-09-09 error date):

- **`hospitalisation_date` (2,111)** -- 1,468 are `r_sent/py_null`, 371
  `r_val/py_sent`, 179 `r_sent/py_val`, 88 `r_val/py_val`. The dominant
  R-sentinel-vs-Python-null shape is the inverse of most causes named so far
  and is not characterized at all. These cells carry free-text clauses
  ("16-Nov-2019 due to DKA"), so ticket 37's prefix fallback is directly
  implicated -- check whether Python's null is a correct "no date recorded"
  or a parse that gives up where R sentinels.
- **`hba1c_updated_date` (1,074) and `fbg_updated_date` (1,032)** -- both
  dominated by `r_val/py_val` (824 and 840): two *real, different* dates on
  each side. That is the hardest shape on the report and the one no cause so
  far explains. `fbg_updated_date` also showed a 1900-01-03 vs 1900-01-04
  pair before ticket 37's fixes -- re-check whether it survives, and whether
  `STRAY_DATE_CLASSIFIERS`'s Excel 1900-leap-year logic applies.
- **`t1d_diagnosis_date` (663)** -- 530 `r_val/py_sent`, i.e. Python's
  future-date guard firing where R carries the date through. Ticket 37
  confirmed one instance of this family is a real source typo, but the
  population was never checked; `python_future_date_sentinel` may simply
  apply, which would be a wiring change rather than an investigation.
- **`t1d_diagnosis_age` (560)** -- what is left after ticket 28's fix and
  ticket 29's `r_numeric_error_sentinel`.
- **A tail of ~50 columns**, none sampled: `observations` (327), the blood
  pressure value pair (`blood_pressure_dias_mmhg` 303,
  `blood_pressure_sys_mmhg` 240), `bmi_date` (190),
  `last_clinic_visit_date` (185), `height` (167), the `fbg_updated` pair
  (163 each).

Carry over one finding ticket 37 deliberately left open: **13 `insulin_type`
rows where both sides hold the same two rows in a different order**, because
`patient_id` + `sheet_name` is duplicated for that patient in that sheet.
Decide whether patient's row-alignment key needs the same treatment product's
did (`add_row_ordinal`, ticket 17) or whether the affected population is
small enough to record and leave -- measure it across all columns first
rather than judging from these 13. [Ticket
31](31-triage-patient-raw-residual-2.md) flagged the same shape on the raw
stage, so whatever is decided here should settle it there too.

Same method: look for systematic shapes, fall back to the real source Excel
trackers as the arbiter (mount at `/Volumes/USB SanDisk 3.2Gen1 Media/a4d/`),
add named causes to the `PATIENT_*_CLASSIFIERS` registries in
`src/a4d/migration/compare.py` (`scripts/compare_outputs.py`'s
`CLASSIFIERS_BY_COLUMN` wires them to columns) -- or fix a real Python bug
directly, as ticket 37 did four times, when one turns up.

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

## Resolution (session-2026-08-14b)

### Decision

**The date sentinel was being stamped on cells that recorded an absence, and
that is a Python defect, not an R divergence.** `parse_date_flexible`
recognized exactly four missing markers (`na`, `nan`, `null`, `none`) where
the numeric path's `safe_convert_column` already recognized eleven. Everything
outside that four-item list -- `-`, `.`, `N/A`, `Nil`, `Unknown`, `?`, and the
tracker template's own leftover instruction text -- reached the error sentinel,
which asserts "a date was recorded and it is invalid" about a cell that plainly
recorded nothing.

Three changes, all in `src/a4d/clean/date_parser.py`:

- `MISSING_VALUE_MARKERS` is now declared once and **shared** with
  `safe_convert_column` (`clean/converters.py`), which had been carrying its own
  copy. The two had drifted; that drift *was* the bug. The numeric path's
  comparison also becomes case-insensitive as a side effect of sharing.
- `DATE_ABSENCE_MARKERS` covers absence written as a word (`nil`, `nill`,
  `unknown`, `unknwon`, `uncertain`, `?`, `no`). Date-scoped deliberately: the
  numeric path stamps 999999 on the same words, and whether it should is a
  separate question this ticket did not reopen.
- `DATE_PLACEHOLDER_FRAGMENTS` catches the template's own instruction text
  left in a data row (`Insert Date`, `Insert Date or NA`,
  `NA or Hospitalisation Date`) -- substring-matched, because clinics copy it
  with varying suffixes.

**R's side of the same shape is now a named cause, and Python is the correct
side.** `r_date_error_sentinel` (`src/a4d/migration/compare.py`, wired across
every column in `get_date_columns()` -- derived, not hand-listed) covers R
stamping `9999-09-09` where Python nulls. R's `parse_dates` tests
`is.na(date)`, which is false for the *string* `"NA"`, so the value falls
through to `lubridate::as_date`, fails, and `convert_to` substitutes
`ERROR_VAL_DATE`.

**Patient's row-alignment key does not need product's positional treatment.**
Measured across all 254 cleaned files: 84 of 85,325 rows (0.10%), in 7 files,
sit on a duplicated `patient_id` + `sheet_name`. Product's key was broken in a
different league (up to 35-way duplication, near-0% row-key match before
ticket 17). The identity key stays; the 84 rows are recorded as a known,
bounded population. **This settles [ticket 31](31-triage-patient-raw-residual-2.md)'s
version of the same question -- it must not be re-derived there.**

### Because

The source file settles the largest column outright. `hospitalisation_date`'s
own sub-header in the tracker template reads **"(Insert Date or NA)"** --
verified directly in `2020_Mahosot Hospital A4D Tracker_DC.xlsx`, sheet
`Jan20`, column 24, where "NA" is what the clinic wrote on nearly every row.
A cell holding "NA" is the form being filled in as designed. Both pipelines'
*raw* stages agree on it (1,565 of the 1,607 cells carrying this shape were
traced back to a raw value of literal `"NA"` on both sides; the remainder
could not be joined to a raw row rather than contradicting it). The
divergence is created entirely at cleaning, by R.

The wider marker set follows the same argument the map already accepted for
`r_numeric_error_sentinel` (ticket 29): a sentinel means "recorded but
invalid", which is the wrong claim for a blank, and it poisons every
downstream aggregate that does not know to exclude it.

### Rejected

- **Wiring `python_future_date_sentinel` across every date column.** This was
  the ticket's own suggestion for `t1d_diagnosis_date` ("may simply apply,
  which would be a wiring change rather than an investigation"), and it is
  wrong. Of the 1,209 cells where Python holds the sentinel and R holds a real
  date, only 722 have an R date beyond the tracker year -- the other 487 are
  Python *failing to parse* something R parsed, which the future-date label
  would have cemented as explained. Split out instead (see below).
- **Extending the numeric path's missing markers to the same word list.**
  Correct in principle, but it moves production numeric output and would
  invalidate ticket 29's exhaustive verification of `r_numeric_error_sentinel`
  in the same session that depends on it. Named in **Not yet specified**.
- **Giving patient a positional row-alignment key.** Measured, not assumed:
  0.10% of rows. The cure costs more than the disease.

### Evidence

**Executed**, not read:

- Full `a4d run patient --force` and `a4d run product --force` against the
  real 254-tracker set on the USB drive (254/254 succeeded on both arms), then
  a full `just compare-outputs` -- baseline run
  `output/comparison/2026-08-14T204031Z`.
- Source-workbook reads: `2020_Mahosot Hospital A4D Tracker_DC.xlsx` (the
  "(Insert Date or NA)" header and its column of "NA" values), and
  `2022_Vietnam National Children_s Hospital A4D Tracker.xlsx` Patient List
  (the 2023-dated cohort, below).
- Raw-vs-cleaned joins across all 254 files to attribute every sentinel-stamped
  date cell to the source text behind it, before and after the fix.
- Full suite 663 passed / 1 skipped, `ruff check`, `ty check src/` all clean.

**Judgement**, not evidence: which words count as an absence.
`nil`/`unknown`/`uncertain`/`?` are unambiguous; `unknwon`/`nill` are typo
spellings observed in this dataset and could be over-fitting. Recorded in
**Assumptions in force**.

### Tense

Every number below describes **current behaviour after this session's fix**,
measured on the 254-tracker set. The before-numbers are the state at
`output/comparison/2026-08-14T200342Z`.

### Numbers

| Measure | Before | After |
|---|---|---|
| Patient cleaned-stage `unclassified` | 8,259 | **6,652** (-19.5%) |
| Patient cleaned-stage total mismatches | 93,997 | 98,097 (+4,100, all newly *explained*) |
| Date cells carrying the sentinel in Python's own output | 6,186 | **1,994** (-68%) |
| ... of those, caused by an unrecognized missing marker | 4,377 | **0** |
| `hospitalisation_date` unclassified | 2,111 | 643 |
| `r_date_error_sentinel` rows | — | 5,707 |

Total mismatches rising is the expected shape, not a regression: Python now
nulls where it previously agreed with R's sentinel by accident, so ~4,100 cells
became a *divergence* -- and every one of them lands in `r_date_error_sentinel`
rather than in `unclassified`.

### A source-corruption finding, recorded not fixed

`t1d_diagnosis_date`'s 530 unclassified rows are 43 patients x 12 sheets in a
single file, `2022_Vietnam National Children's Hospital A4D Tracker`. Its
Patient List records **2023** diagnosis dates for the whole cohort, and those
dates are internally consistent with the same sheet's D.O.B. and Age-at-
Diagnosis columns (VN_VC001: dob 2013-03-03, diagnosis 2023-07-16, age 10).
So neither pipeline misparsed anything -- the workbook is a 2022-named,
2022-sheeted tracker holding 2023 data. Python's future-date guard flags it
and R propagates it; per the map's Notes, **"the source is wrong, this tracker
needs human inspection" is the terminal answer here.**

### Split off

The 487-row parse-failure population and its production twin -- 1,809 date
cells across 296 distinct source texts where a real date sits inside a
clinical note (`"DKA 23 Oct 2020"`, `"Passed away 28/10/2019 due to DKA"`) and
Python discards it -- became [ticket
39](39-recover-dates-embedded-in-free-text.md). It is a production-behaviour
decision, not triage: R recovers some of these and is demonstrably wrong on
others (`"admitted ... DKA 7-15 Apr"` -> R gives 2015-07-01), so "do what R
does" is not available as an answer.
