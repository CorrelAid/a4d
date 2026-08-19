---
id: 54
title: Triage the residual patient cleaned-stage mismatches (round 7)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-19d
claimed_at: 2026-08-19T21:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 53
---

## Premise

Rests on [round 6](53-triage-patient-cleaned-residual-6.md), closed, which took
the cleaned-stage in-scope residual from 2,278 to **1,689** by fixing two Python
defects rather than labelling them. Read its resolution before starting; it
settles three things this ticket must not re-open:

- **`parse_date_flexible` no longer lets dateutil invent a component from
  today.** An absent day resolves to the 1st; an absent month or year makes the
  cell unparseable. Do not re-add a month-year spelling to the pattern -- the
  probe-the-defaults mechanism closes the class.
- **`split_bp_in_sys_and_dias` trims each fragment**, so a source written
  `70 / 40` keeps its reading. Blood pressure has left the residual; do not
  expect it back.
- **`hospitalisation_date` (489) is entirely [ticket
  39](39-recover-dates-embedded-in-free-text.md)'s**, in all three of its
  directions, including the newly measured one where *both* pipelines find a
  date and disagree about which of several admissions the cell means. It is
  deliberately left unclassified. Do not triage it here and do not label it.

Rests on the six cleaned-stage rounds before it
([1](29-triage-patient-cleaned-residual.md),
[2](37-triage-patient-cleaned-residual-2.md), [the date
family](38-triage-patient-cleaned-date-family.md), [round
4](51-triage-patient-cleaned-residual-4.md), [round
5](52-triage-patient-cleaned-residual-5.md), [round
6](53-triage-patient-cleaned-residual-6.md)), on the map's standing scoping rule
that the current tracker template is the golden rule, and on the standing bar
that a classifier records understanding, never a verdict by itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **1,689** in-scope cells left on run
`output/comparison/2026-08-19T185253Z`, excluding `fbg_updated_mmol` ([ticket
44](44-triage-cleaned-fbg-r-null-residual.md)) and `hospitalisation_date`
(ticket 39). Re-measure before working any shape -- every round so far has found
at least one stated shape had already moved.

The method that found both of round 6's defects, and round 5's: **join the
flagged cells back to Python's own raw stage and group by the *source* value**,
not by the shape of the two outputs. A population that is homogeneous at the
source is a mechanism; one that is only homogeneous in the report may be a
coincidence.

- **`t1d_diagnosis_age` (298)** -- now the largest takeable shape, measured by
  round 6 but deliberately not decided. Three sub-shapes, all of which look
  decidable:
  - *R null, Python derives an age* (dominant; 2024/2025/2026 Sarawak, 2021
    Children's Hospital 2). Both `dob` and `t1d_diagnosis_date` are present on
    Python's side and R failed to parse one of them -- for Sarawak these are the
    bare-year dates [round 5](52-triage-patient-cleaned-residual-5.md)
    recovered, so this is likely a downstream face of `python_reads_bare_year`
    that `python_age_from_bare_year` does not catch, because extraction now
    resolves the bare year before the classifier can see it.
  - *R 999999, Python 0*: the source records an age in words -- `4 months`,
    `4mth`, `At birth` (2017/2018 Mandalay, 2017/2018 Yangon) -- which R cannot
    parse, while Python derives 0 from the two dates.
  - *R 20668, Python null*: 2023 Chiang Mai has a **date** (`1956-08-01`) typed
    into the age column; R carries the Excel serial into the age, Python nulls
    it. A [ticket 40](40-source-defect-findings-report.md) source-defect
    finding if it holds.
- **The smaller date columns** -- `hba1c_updated_date` (108),
  `fbg_updated_date` (101), `bmi_date` (88), `recruitment_date` (58),
  `last_clinic_visit_date` (41), `lost_date` (18), `t1d_diagnosis_date` (12),
  `dob` (7), `last_remote_followup_date` (3). Round 6 established that
  `hospitalisation_date` is *all* clinical notes; whether the same holds for
  these is unmeasured. Split each by direction (Python sentinels / R sentinels /
  both real and differing) before deciding, and hand any clinical-note share to
  ticket 39 rather than triaging it.
- **`height` (114)**, **`fbg_updated_mg` (113)**, **`bmi` (22)** -- untouched by
  rounds 4, 5 and 6. `bmi` is formula-derived in the source, so
  `excel_formula_error` is the raw-stage cause; what survives cleaning is a
  different question.
- **The long tail (~200)**:
  `complication_screening_lipid_profile_cholesterol_value` (72),
  `insulin_subtype` (67), `complication_screening_kidney_test_value` (60),
  `hba1c_updated` (8), `fbg_baseline_mg` (6), and the columns in single digits
  -- including the four `clinic_visit`/`remote_followup` rows the map's **Not
  yet specified** section has been carrying since ticket 49, which belong with
  whatever round works the tail.

Split further rather than leaving this open-ended if it does not converge -- six
rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.

## Resolution

**Decision.** `t1d_diagnosis_age` (298) and the two string-typed screening
measurement columns (132) are fully explained and decided; the cleaned-stage
in-scope residual falls **1,200 -> 770** (36%), the raw stage holds at **0**,
and total cleaned-stage cell mismatches fall 114,712 -> 114,580. No pipeline
behaviour changed: both findings are R limitations or comparison-harness gaps,
not Python defects. Everything else measured this session is handed to [round
8](55-triage-patient-cleaned-residual-8.md) with its mechanism already named.

A note on the count: this ticket's own premise said 1,689 in-scope. The
measured figure is 1,200 -- 4,625 unclassified less `fbg_updated_mmol` (2,936)
and `hospitalisation_date` (489). 1,689 is 1,200 plus the 489 this ticket
excludes from work; the frontier was the same either way.

**`t1d_diagnosis_age` (298 -> 0), two causes, Python right in both.**

`r_never_derives_diagnosis_age` (282). R's `fix_t1d_diagnosis_age` exists in
`script2_helper_patient_data_fix.R` and is unit-tested against exactly the
strings the trackers carry -- "At birth", "4 months", "5y", "10y10m" -- but its
**call site is commented out** (`script2_process_patient_data.R:251`, read
directly, not inferred). So R's `t1d_diagnosis_age` is only ever the source
column through `as.numeric`: a blank cell stays NA, a cell written in words
becomes R's 999999 "recorded but invalid" sentinel. Python's
`_fix_t1d_diagnosis_age` fills from `dob` and `t1d_diagnosis_date` in exactly
those two cases and otherwise keeps what the clinic recorded.

Python is right on the source's own evidence, not on the shape of the diff.
Where the source wrote the age in words, Python's derived figure agrees with
the words: 2017 Mandalay's MM_MD010 reads `11yr` against a D.O.B. of
2004-03-01 and a diagnosis of 2016-01-01, and Python derives 11; MM_MD011
reads `4mth` against 2013-10-23 and 2014-02-01, and Python derives 0. Where
the cell is blank, both pipelines hold the *same* two dates and only Python
uses them -- 2024 Sarawak's MY_SW001 is (2000-06-30, 2011-01-01) on both sides,
null in R and 10 in Python. R keeps nothing a clinic recorded; Python recovers
information R discards.

`source_date_in_diagnosis_age` (16). A date typed into the `Age at Diagnosis`
column, confirmed in both source workbooks. 2023 Chiang Mai's Patient List row
for TH_CP005 holds 1956-08-01 (serial 20668) in a workbook whose `Date of T1D
Diagnosis` column is empty for **every** patient, so its formula-derived age
column reads `#NUM!` throughout; 2023 Yangon General's row for MM_YC043_YG
holds 2017-05-04 (serial 42859) against a D.O.B. of 2008-01-01 and a diagnosis
date of 2007-06-01 -- a diagnosis a year before the birth. R's readxl reads
the column as numeric and carries the raw serial into the age; Python's cast
fails and the cell is null. Python is right (20,668 is not an age), and both
are source defects for [ticket 40](40-source-defect-findings-report.md).

Why these 298 were not already `python_age_from_bare_year` (ticket 52): that
classifier fires on `row_has_bare_year_date`, which requires the row's own date
cells to *disagree*. Sarawak's 2024 workbook writes real 1-January dates, so R
and Python agree on the dates and no bare-year mismatch exists on the row --
the ages differ purely because only Python derives one. The ticket's stated
hypothesis (a downstream face of `python_reads_bare_year`) was therefore
wrong, and the real mechanism is more general.

**The screening measurement columns (132 -> 0), a harness gap.**
`complication_screening_lipid_profile_cholesterol_value` (72) and
`complication_screening_kidney_test_value` (60) were entirely
`4.8600000000000003` against `4.86` -- the float-to-string rounding difference
`normalize_numeric_column` has handled since ticket 22, which was scoped to the
raw stage on the argument that cleaning casts its numeric columns. That
argument has an exception nobody had measured: the cleaned schema types these
columns as **String** (verified in both pipelines' own parquet schemas) because
the same cell can read "normal", so cleaning never casts them and the artifact
survives. Added `string_numeric_normalize_targets` (derived from each frame's
own dtypes, not a named list) and wired the `Patient (cleaned)` stage to it via
a new `ALL_STRING_COLUMNS` sentinel. The 132 cells stop being mismatches at
all rather than being labelled -- total mismatches fell by exactly 132, so
nothing already classified was masked.

**Rejected.**
- *Labelling the 298 as a bare-year effect*, per the ticket's own hypothesis.
  Killed by measurement: R's and Python's dates are identical on the dominant
  Sarawak population, so there is no bare-year mismatch to be downstream of.
- *One classifier for all 298.* The 16 date-in-age cells have the opposite
  direction (Python nulls, R carries) and a different verdict (the source is
  broken, not R), so folding them in would have hidden a ticket 40 finding
  behind an R-limitation label.
- *Naming the two screening columns explicitly.* Rejected per the map's
  never-hand-maintain rule -- which columns the schema types as strings is the
  schema's decision, and a copy of it drifts.
- *Chasing `height`, `fbg_updated_mg`, `bmi`, `insulin_subtype` here.* Each was
  measured far enough to name its mechanism and two of them look like real
  Python defects; that is more than one session and is round 8's work.

**Evidence.** Executed. R's dead call site read directly from
`r-archive/R/script2_process_patient_data.R`; both source workbooks opened with
openpyxl and the offending cells printed; the mismatch population joined back
to Python's own raw stage per the ticket's prescribed method; verdicts checked
against the real 248-tracker `output_r`/`output_python` pair on the USB drive.
Two full comparison runs (`2026-08-19T195136Z`, `2026-08-19T195625Z`) measured
the before/after. Full suite 799 passed / 1 skipped, ruff and `ty check src/`
clean.

**Tense.** Every count above is current behaviour of the code as committed,
measured on run `2026-08-19T195625Z`, not a consequence of a proposed design.

**Also corrected in passing.** `clean/patient.py`'s step 5.5b comment still
read "Replaces any existing value (including Excel errors like #NUM!)", which
ticket 52 made false -- the function now prefers the tracker's own recorded
age. Same class of correction as round 4's `_validate_dates` docstring.
