---
id: 53
title: Triage the residual patient cleaned-stage mismatches (round 6)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-19c
claimed_at: 2026-08-19T18:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 52
---

## Premise

Rests on [round 5](52-triage-patient-cleaned-residual-5.md), closed, which took
the cleaned-stage in-scope residual from 2,538 to **2,278** by settling
`t1d_diagnosis_age` -- and found two real Python bugs doing it, not a labelling
job. Read its resolution before starting; it decides three things this ticket
must not re-open:

- **A bare four-digit year in a date cell is recovered as 1 January of that
  year**, in `parse_date_flexible` *and* in `read_patient_rows` (the second is
  needed only where the cell is date-formatted). The Sarawak cross-year
  evidence settles that Python is right. Do not re-argue it as a source defect.
- **A derived `t1d_diagnosis_age` that goes negative is nulled**, because the
  source's two dates contradict each other. The workbooks are the thing to
  correct -- a [ticket 40](40-source-defect-findings-report.md) finding.
- **`row_has_bare_year_date`** now exists on `CellMismatch`, set across the
  whole row by `compare_cells`. It is the precedent for keying a *derived*
  column's cause on the mechanism rather than on the derived values' shape.

Rests on the five cleaned-stage rounds before it
([1](29-triage-patient-cleaned-residual.md),
[2](37-triage-patient-cleaned-residual-2.md), [the date
family](38-triage-patient-cleaned-date-family.md), [round
4](51-triage-patient-cleaned-residual-4.md), [round
5](52-triage-patient-cleaned-residual-5.md)), on the map's standing scoping
rule that the current tracker template is the golden rule, and on the standing
bar that a classifier records understanding, never a verdict by itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **2,278** in-scope cells left on run
`output/comparison/2026-08-19T174047Z`. Re-measure before working any shape --
every round so far has found at least one stated shape had already moved, and
round 5 moved two of them in the *upward* direction by making Python more
correct.

`fbg_updated_mmol` (2,936) is **not** this ticket's work -- it is [ticket
44](44-triage-cleaned-fbg-r-null-residual.md). Exclude it and confirm the
exclusion by column before starting.

- **`hospitalisation_date` (546)** -- now the largest single shape in scope.
  Round 4 measured this population by joining the sentinelled cells back to
  `patient_data_raw`: Python stamps the date sentinel on a cell it could not
  parse at all, and R guesses -- badly, reading `9-Dce-20` as 2020-09-01. It
  splits into two kinds, and **only the first is takeable here**:
  - *A mangled date token and nothing else* (`9-Dce-20`, `25-Ma4-2025`,
    `4-Okt-2023`, `26/102022`, `19-Jan_2023`). Round 4's verdict, if it holds
    on re-measurement, is that Python is right to refuse and the workbook is
    what needs correcting -- a [ticket 40](40-source-defect-findings-report.md)
    finding.
  - *A date buried in a clinical note* (`DKA - Feb-2020`, `26 Jun (ceton urine
    high)`, `DKA; Jul 2018`). This is [ticket
    39](39-recover-dates-embedded-in-free-text.md)'s open HITL question. Do not
    decide it here; measure it and leave it.
  The same split governs the smaller date columns: `hba1c_updated_date` (108),
  `fbg_updated_date` (103), `bmi_date` (94), `recruitment_date` (72),
  `last_clinic_visit_date` (41), `lost_date` (18).
- **Blood pressure (491)**: `blood_pressure_dias_mmhg` (289),
  `blood_pressure_sys_mmhg` (202). These columns already carry
  `r_extraction_gap` for the 2026 template's Annual sheet, so the residual is
  something else.
- **`t1d_diagnosis_age` (298 left)** -- the share round 5 did *not* explain.
  590 of 597 `age` mismatches proved to sit on a bare-year row, but only 239 of
  537 diagnosis-age ones did, so the remainder is a different mechanism.
  Round 5 found two of its shapes without deciding them: R stamps the 999999
  sentinel where the source records an age with a unit (`11yr`, `4mth`, 2017
  Mandalay) that Python parses, and R carries a raw Excel serial (20668) into
  the age column in 2023 Chiang Mai where Python has null.
- **`height` (114)**, **`fbg_updated_mg` (113)**, **`bmi` (22)** -- untouched
  by rounds 4 and 5. `bmi` is formula-derived in the source, so
  `excel_formula_error` is the raw-stage cause; what survives cleaning is a
  different question.
- **The long tail (~300)**:
  `complication_screening_lipid_profile_cholesterol_value` (72),
  `insulin_subtype` (67), `complication_screening_kidney_test_value` (60), and
  the columns in single digits -- including the four
  `clinic_visit`/`remote_followup` rows the map's **Not yet specified** section
  has been carrying since ticket 49, which belong with whatever round works the
  tail.

Split further rather than leaving this open-ended if it does not converge --
five rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.

## Resolution

**Decision.** Two of the three shapes this round set out to explain turned out
to be **Python defects, both fixed**; the third -- `hospitalisation_date`, the
largest single column in scope -- turned out to be **entirely** [ticket
39](39-recover-dates-embedded-in-free-text.md)'s open question and is handed
there rather than triaged here. The in-scope residual went **2,278 -> 1,689**
(26%) and the patient raw stage held at 0 unclassified. What is left became
[round 7](54-triage-patient-cleaned-residual-7.md).

### 1. dateutil completed an absent day from today (fixed)

`parse_date_flexible` (`src/a4d/clean/date_parser.py`) has an alphabetic
month-year branch precisely so a month-and-year cell resolves to the first of
the month rather than being handed to `dateutil.parser.parse`, which fills any
absent field from `datetime.now()`. The branch's pattern only ever matched an
alphabetic month with a hyphen or space, so three spellings still reached
dateutil: the **numeric** form (`10/2019`), the **comma-separated** form
(`Mar, 2017`, `August,2015`, `June ,2016`), and the **apostrophe** form
(`Jun'09`, `Apr'21`). Ticket 50 hit this same fill through a rich-text-damaged
`July2014` and closed that one route into it.

Verified by execution, not by reading: `parse_date_flexible("10/2019")`
returned **2019-10-19** on 19 August, and `"06/2020"` returned 2020-06-19 --
the day is the run date's day of month. 42 raw cells across five date columns
(`hospitalisation_date` 24, `fbg_updated_date` 9, `hba1c_updated_date` 4,
`last_remote_followup_date` 3, `bmi_date` 2) carry a source in this shape, so
that many production values changed meaning from one run to the next with no
input change.

The fix is deliberately **not** another spelling added to the pattern.
`_parse_with_dateutil` parses the string twice against two disjoint defaults
(1111-01-01 and 2222-02-02); a component that differs between the two parses is
one dateutil invented rather than read. An invented **day** resolves to the 1st
-- the same convention the alphabetic branch already uses -- and an invented
**month or year** makes the cell unparseable, because neither is recoverable
from the string and today's date is not an answer. Two supporting corrections
came out of running it over all 5,185 distinct raw date strings: the
apostrophe was admitted to the month-year separator class (`May'21` had been
read as the 21st of May *this* year, now 2021-05-01), and
`_parse_longest_parseable_prefix` now skips a bare number below the bare-year
floor (truncating `26 Jun (ceton urine high)` down to `26` had made it Excel
serial 26, i.e. 1900-01-25).

Of the 5,185 distinct sources, **36 parse differently**; every one was checked
by hand. 23 move from a today-filled day to the 1st of the correct month; the
rest move from a confidently wrong date to the error sentinel (`Sep` was
2026-09-19, `3 month come back meet Doctor` was 1900-01-02, three Thai-script
dates were 1900-01-0x). None moves from a right answer to a wrong one.

**Verdict: Python was wrong and is now right.** R is not the reference here --
R sentinels most of these -- but a value that depends on the calendar date of
the run is indefensible on its own terms.

### 2. A blood pressure with a space beside the slash was discarded (fixed)

All 491 in-scope `blood_pressure_sys_mmhg` / `blood_pressure_dias_mmhg` cells
had the identical shape: R holds a plausible reading (100, 60, 70, 40) and
Python holds the 999999 numeric error sentinel. Joining them back to Python's
own raw stage showed **every single affected source value has whitespace
around the slash** -- `70 / 40`, `103/  69`, `116  / 66`, `105/ 62` -- and
nothing else wrong with it.

`split_bp_in_sys_and_dias` (`src/a4d/clean/transformers.py`) splits on `/` and
leaves the padding on each fragment. R's `separate_wider_delim`
(`script2_helper_patient_data_fix.R:645`) leaves it on too, but R's
`as.numeric` ignores surrounding whitespace where Polars' cast fails on it --
so the identical intermediate value survives in R and becomes the error
sentinel in Python. The fragments are now trimmed.

Measured end-to-end against the real 248-tracker drive data:
`blood_pressure_dias_mmhg` **302 -> 13** total mismatches,
`blood_pressure_sys_mmhg` **215 -> 13**; both columns leave the unclassified
residual entirely. 465 cells across 7 trackers (2019/2020/2021 Mandalay,
2019/2020/2021 CDA, 2021 Sunprasitthiprasong) had a recorded blood pressure
restored.

**Verdict: Python was losing information the source carried, and R was right.**
This is the map's ticket-27 precedent again -- a classifier here would have
cemented a data-loss bug as "explained".

### 3. `hospitalisation_date` is ticket 39's population, not this round's

The ticket expected this column to split into *a mangled date token and
nothing else* (takeable here) and *a date buried in a clinical note* (ticket
39's). **On re-measurement that split does not exist for this column.** All
546 cells were joined back to the raw stage and grouped by source value; every
distinct source is a clinical note. The three directions are:

- **Python sentinels, R has a date (302)**: `DKA - Feb-2020`, `DKA; Jul 2018`,
  `Passed away 28/10/2019 due to DKA`, `DKA 2020: June, Aug, Nov`.
- **R sentinels, Python has a date (179)**: `April 19 (due to very high
  Hba1c)`, `19th-29th Aug 2019`, `7/2020 DKA Admit Ratchaburi Hospital 5
  Days`. Python already recovers dates from free text in these; R does not.
- **Both have a date and they differ (65)**: `May 2019, Dec 2019 DKA, August
  2020 DKA` -- the cell lists *several* admissions and the two pipelines pick
  different ones.

That third direction is the substantive new finding: the question is not only
"recover or discard" but **which** date, when the cell records more than one.
It is recorded on ticket 39 rather than decided here.

Deliberately **not** classified. Naming a cause would move 489 cells out of
`unclassified` while the decision that governs them is still open, which is
exactly what the map's standing bar forbids. They stay visible.

### Because

The two fixes were found the same way the last four rounds found theirs: join
the flagged cells back to Python's own raw stage and group by the *source*
value, rather than by the shape of the two outputs. Both populations were
100% homogeneous at the source once looked at that way -- every BP cell had a
space by the slash, every hospitalisation cell was prose -- which is what
distinguishes a mechanism from a coincidence.

### Rejected

- **Adding `10/2019` (and then `Mar, 2017`, and then `Jun'09`) to the
  month-year pattern.** This is what ticket 50 did for `July2014`, and this
  round is the second time the same fill has resurfaced through a spelling
  nobody enumerated. Probing dateutil's defaults closes the class instead of
  the instance. What it gives up: three sources that previously produced a
  confidently wrong date now produce the sentinel (`26-05- 2007`, a real date
  broken by a stray space, is the one genuine loss) -- accepted, because the
  old answers were wrong, not merely imprecise.
- **Normalizing whitespace around date separators** so `26-05- 2007` parses.
  Correct-looking and untested across the other 5,184 sources; a third
  normalization in one session is how a triage round turns into a regression.
  Left as a [ticket 40](40-source-defect-findings-report.md) source-defect
  finding.
- **Trimming inside `safe_convert_column` instead of in the BP splitter.**
  Would have silenced the symptom for every numeric column at once and hidden
  that the splitter is what introduced the padding. It also risks
  re-classifying cells ticket 29 verified exhaustively under
  `r_numeric_error_sentinel`.
- **Classifying `hospitalisation_date` as `date_inside_clinical_note`.** See
  above -- a label there would read as "understood and settled" when the
  decision is open.
- **Working `t1d_diagnosis_age` (298).** Measured, not decided: it is three
  shapes -- R null where Python derives an age from a `dob`/`t1d_diagnosis_date`
  pair R failed to parse (dominant, mostly Sarawak's bare-year dates from
  ticket 52); R's 999999 where the source records an age in words (`4 months`,
  `At birth`, `4mth`) and Python derives 0 from the dates; and 2023 Chiang
  Mai, where a *date* (`1956-08-01`) is typed into the age column and R carries
  Excel serial 20668 into it while Python nulls it. All three look decidable,
  none is decided here -- the session had already changed the pipeline twice
  and re-run it twice. Carried to round 7 with these measurements.

### Evidence

**Executed:** every count in this resolution. The parser probes were run
against the installed module; the 36-source diff was produced by running the
old and new parser over all 5,185 distinct raw date strings; the before/after
mismatch counts come from two full pipeline runs against the real 248-tracker
set on the USB drive and the comparison tool's own run-over-run delta
(baseline `2026-08-19T174047Z`, intermediate `2026-08-19T184342Z`, final
`2026-08-19T185253Z`). Full suite 788 passed / 1 skipped, ruff and
`ty check src/` clean. Pushed as `f16101e`.

**Read:** R's `split_bp_in_sys_and_dias`
(`r-archive/R/script2_helper_patient_data_fix.R:623-653`) was read, not run --
the claim that R's `as.numeric` tolerates surrounding whitespace is R language
behaviour taken on knowledge, and the *observable* fact executed instead is
that R's frozen output holds the value where Python's held the sentinel. That
is the load-bearing half, so no assumption is recorded for it.

**Tense:** every count describes current behaviour after the fixes, except the
"was 2019-10-19" and "302 -> 13" readings, which describe behaviour before
them.
