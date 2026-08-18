---
id: 50
title: Triage the residual patient raw-stage column mismatches (round 6)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-18b
claimed_at: 2026-08-18
resolution: decided
evidence: executed
closed_by: null
spawned_by: 49
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches (round
5)](49-triage-patient-raw-residual-5.md), closed, which took patient raw-stage
unclassified from **229 to 84** by settling three causes: the whitespace target
list being derived from the cleaned schema rather than the raw stage (comparison
fix, 40 rows), R's and Python's spellings of an Excel boolean (comparison fix,
20), R's Unicode-aware header sanitizer missing a header carrying a local-
language translation (`r_non_latin_header_miss`, 44), and the 2026 template's
Annual sheet reaching columns ticket 37's `r_extraction_gap` had not been
registered for (41).

The residual is **84**, measured on baseline run
`output/comparison/2026-08-18T135258Z`, which is the run to triage against.

Rests also on the map's standing scoping rule that the current tracker template
is the golden rule, and on the standing bar that a classifier records
understanding, never a verdict by itself.

## Question

Triage the 84. Re-measure against the baseline run before working any shape --
ticket 49 found that two of its predecessor's stated shapes had already moved.

- **`fbg_updated_date` (25, one file)**: `2019_Preah Kossamak`, all R-null with
  Python holding a value. Shape-identical to `r_extraction_gap`, but ticket 31's
  refusal applies and ticket 49 honoured it: verify the mechanism against the
  source workbook before wiring, since ticket 49 found this file has *no*
  non-Latin header divergence, so it is not the Mukdahan cause.
- **`t1d_diagnosis_date` (23, two files)**: R 41838 vs Python 41821 in
  `2017_Yangon` -- two different real dates 16 days apart, so neither side is
  null and neither is obviously right. Unexplained, and carried unexplained
  through rounds 5 and 6.
- **`t1d_diagnosis_age` (16, two files)**: a real date typed into a numeric
  column, or the reverse. Ticket 49's predecessor recorded this as a source
  defect -- if that holds, it is a finding for [ticket
  40](40-source-defect-findings-report.md) rather than a pipeline change.
- **`hospitalisation_date` (5) and `hospitalisation_cause` (3)**: both
  `2022_Kantha Bopha`, both R-null. `hospitalisation_date`'s Python values
  include `2958352`, the Excel serial for 9999-12-31 -- the date sentinel
  appearing at the *raw* stage, which raw is not supposed to carry. Ticket 49
  did not establish whether the sentinel is in the source workbook or is Python
  applying a cleaning-stage rule too early; that is the load-bearing question.
- **`clinic_visit` (5, one file)**: `2025_LWCH`, R-null against Python `Y`.
  Distinct from the 10 boolean-spelling rows ticket 49 resolved in the same
  column -- do not assume the boolean fix covers it.
- **`blood_pressure_mmhg` (3)**, **`complication_screening` (2)**,
  **`testing_frequency` (1)**, **`observations` (1)**: long tail, neither side
  null except where noted. `observations`'s single row is R's `... January ,NA`
  against Python's `... January`, where `r_na_unite_padding` does not fire (the
  trailing space before the comma is the likely reason).

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

**Decision.** All 84 triaged, and the patient raw stage now has **zero**
unclassified mismatches. Six mechanisms, none of them a Python defect:

1. **R never mapped the column at all** -- 38 rows, three separate header
   defects, all `r_extraction_gap` (the docstring now records each). 2022
   Kantha Bopha's hospitalisation header opens with thirteen spaces, so R's
   sanitizer emits `xcurrentmonthhospitalisationdkahypootherdropdown` -- the
   same leading-space mechanism ticket 37 found on `edu_occ_updated`, and R's
   own raw parquet carries the junk column to prove it (5 `hospitalisation_date`
   + 3 `hospitalisation_cause`). 2019 Preah Kossamak's `Jul19`/`Aug19` sheets
   have lost every header merge the other ten still have, so "Updated FBG" no
   longer spans its "Date" sub-header; R is left with a bare `date` column and
   reads **0** values for those two sheets against Python's 13 and 12 (25
   `fbg_updated_date`). 2025 LWCH leaves the clinic-visit column unheaded in
   both header rows, so R drops it and ticket 30's `recover_blank_headers`
   names it from the sibling sheets (5 `clinic_visit`).
2. **A date typed into a numeric column** -- 20 rows, wired to the existing
   `openpyxl_date_typed_stray_cell` ticket 24 root-caused on the product arm.
   R's readxl coerces the column to its majority numeric type and carries the
   Excel serial; Python's openpyxl honours the cell's own date format. Each of
   the five serials decodes to exactly Python's value (20668 -> 1956-08-01,
   42859 -> 2017-05-04, 22190 -> 1960-10-01, 25873 -> 1970-11-01, 44228 ->
   2021-02-01), and every source cell is genuinely date-formatted. A source
   defect, reported to [ticket 40](40-source-defect-findings-report.md).
3. **R drops a whitespace-only rich-text run, and the harness then dated the
   damage** -- 11 rows. 2017 Yangon Children's `Feb17!I66` is the rich-text
   string `July` / ` ` / `2014` (read out of the workbook's own
   `sharedStrings.xml`); readxl loses the middle run, so R's raw holds
   `July2014` where Python's holds `July 2014`. Both are the same cell, but
   `MONTH_NAME_PATTERN` required a word boundary after the month name -- which a
   digit does not provide -- so the month-year branch never saw `July2014` and
   dateutil filled the day **from today**, producing 2014-07-18 against Python's
   2014-07-01. The pattern now ends in a negative lookahead. This was a live
   non-determinism: the same comparison run on a different day produced a
   different number.
4. **A Buddhist-Era serial too large for the parser's ceiling** -- 12 rows.
   2022 Hat Yai `Patient List!G25` holds 2560-01-01 (serial 241062);
   `parse_date_flexible` only treated a number below 100000 as an Excel serial,
   so 241062 fell through to dateutil, which read the digits positionally as
   24/10/62. The ceiling is now `MAX_EXCEL_DATE_SERIAL = 256_000` (~year 2600),
   deliberately below the numeric error sentinel 999999 and the largest observed
   non-date value (1,141,523). Both sides now decode to the same date, so the
   mismatch disappears rather than being labelled -- and so do **363** rows that
   `buddhist_era_typo` had been absorbing (369 -> 6) because R's side had been
   sentinelling an unparseable serial.
5. **R keeps only the first selection of a multi-select block** -- 2 rows, the
   new `r_duplicate_header_selection_dropped`. 2021 NPH `Dec21!AD84`/`AE84` are
   two "(Select)" sub-columns of one merged screening header; R's
   `make.names(unique = TRUE)` suffixes the duplicate and its mapping keeps only
   the first -- proven in R's own raw parquet, which parks "Foot Examination
   (Nerves)" in `complicationscreeningselect1`. Python unites both. Fires only
   where R's value is exactly Python's first selection.
6. **Two verified causes stacked in one cell** -- 1 row.
   `r_na_unite_padding` compared the surviving parts untrimmed, so a source
   value ending in a space (`... January ,NA` against `... January`) matched
   neither it nor ticket 46's `python_trims_merged_subvalue`. Parts are now
   compared trimmed, which cannot absorb an interior whitespace difference.

**Because.** Every one of the six was checked against the source workbook or
against R's own output before a classifier was written, per ticket 31's refusal
to wire on shape alone -- and that refusal earned its keep twice. The
`fbg_updated_date` population is shape-identical to `r_extraction_gap` but its
mechanism (lost header merges) is unrelated to any previously recorded one, and
the ticket's own load-bearing question -- whether Python was stamping the date
sentinel at the raw stage -- turned out to have a third answer: Python's raw
holds the verbatim text `on stamlor 5mg`, and the `9999-09-09` in the report was
the **comparison harness's** own date normalization of it. No raw-stage
sentinel, no pipeline bug.

**Rejected.**
- *Naming the `fbg_updated_date` population `r_extraction_gap` on its shape.*
  Refused until the mechanism was traced; it turned out to be a fourth,
  genuinely different mechanism, now documented rather than merged silently
  into the other three.
- *Giving the Buddhist-Era serial its own classifier.* A classifier would have
  recorded a difference that does not exist: both sides hold the same cell, and
  only the parser's ceiling made them disagree. Fixing the parse removes 375
  rows from the report instead of labelling 12.
- *Leaving `MAX_EXCEL_DATE_SERIAL` alone and special-casing the harness.* The
  harness reuses `parse_date_flexible` on purpose. Measured before changing it:
  95 values across all 254 R raw files sit above the old ceiling, 93 of them in
  the 241k-245k BE band and two far outside it, so the new ceiling takes exactly
  the BE band. Production output is unchanged -- Python's own raw never carries
  these as text (openpyxl returns datetimes), and the cleaned stage's
  future-date guard sentinels the decoded date exactly as it sentinelled the
  unparseable one.
- *Fixing the source workbooks in the pipeline.* Six findings are workbook
  defects (three header defects, two dates in numeric columns, one clinical
  note in a date column, one BE year); all went to
  [ticket 40](40-source-defect-findings-report.md) per the map's standing rule.
- *A round 7.* Nothing is left to split: the raw stage is at zero.

**Evidence.** `executed` throughout. The 84 and all 13 column/file shapes were
re-measured off the stated baseline before any work, and every shape matched the
ticket. Source claims were read out of the real workbooks on the drive
(including `sharedStrings.xml` for the rich-text run) and cross-checked against
R's own raw parquet. Final comparison run
`output/comparison/2026-08-18T214952Z` against the full 254-tracker drive data:
patient raw total mismatches 26,557 -> 26,171, **unclassified 84 -> 0**; patient
cleaned unclassified 8,008 -> 7,967 and `r_extraction_gap` +40, from the same
wiring reaching the cleaned stage; product raw and cleaned unchanged (0 and 20
unclassified). Per-cause deltas match the six mechanisms exactly:
`r_extraction_gap` +38, `openpyxl_date_typed_stray_cell` +20,
`r_duplicate_header_selection_dropped` +2, `r_na_unite_padding` +1,
`buddhist_era_typo` -363. Full suite 759 passed, 1 skipped (+6 new tests), ruff
clean.

**Tense.** Every count is current behaviour, measured after the change.
