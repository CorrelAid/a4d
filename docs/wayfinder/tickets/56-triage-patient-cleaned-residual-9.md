---
id: 56
title: Triage the residual patient cleaned-stage mismatches (round 9)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-19f
claimed_at: 2026-08-19
resolution: decided
evidence: executed
closed_by: null
spawned_by: 55
---

## Premise

Rests on [round 8](55-triage-patient-cleaned-residual-8.md), closed, which took
the in-scope cleaned residual from 770 to **448** and settles four things this
ticket must not re-open:

- **`height`, `bmi` and `fbg_updated_mg` are decided.** Python's cm-to-m
  threshold now matches R's 50, BMI is derived after the height cut, and R's
  `fix_fbg` is confirmed to manufacture readings from text. Do not re-triage
  them; if one reappears, a fix regressed.
- **`parse_date_flexible` now rejects any year below 1900.** A date in
  antiquity is no longer reachable from a source year typed short. The date
  columns below are what survives that fix, not what preceded it.
- **`insulin_subtype`'s drug-name rows are recovered** and only the 11
  `Undefined`-against-null cells remain.
- **An unticked insulin row keeping `Undefined` is deliberate**, not an
  oversight: R publishes the same on 17,418 rows where the two pipelines agree.
  It is fog on the map, not this ticket's to change.

Rests on the eight cleaned-stage rounds before it, on [ticket
42](42-fbg-unit-headers-and-implausible-values.md) for the FBG analytical
bounds, on the map's rule that the current tracker template is the golden rule,
and on the standing bar that a classifier records understanding, never a
verdict by itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **448** in-scope cells left on run
`output/comparison/2026-08-19T205332Z`, excluding `fbg_updated_mmol` ([ticket
44](44-triage-cleaned-fbg-r-null-residual.md)) and `hospitalisation_date`
([ticket 39](39-recover-dates-embedded-in-free-text.md)). Re-measure before
working any shape.

- **The date family (412), which is now almost the whole residual.**
  `hba1c_updated_date` (103), `fbg_updated_date` (91), `bmi_date` (87),
  `recruitment_date` (58), `last_clinic_visit_date` (40), `lost_date` (18),
  `t1d_diagnosis_date` (12), `dob` (7), `last_remote_followup_date` (3). Round
  8 measured the direction split rather than the causes, and killed the obvious
  framings: only **2** of 414 are a day/month swap and **none** is a year-only
  difference, so this is not a systematic parse-order divergence. It is
  concentrated by tracker instead -- 2021 Mahosot DC and 2020 Mahosot DC
  together account for roughly 150, and within them R and Python each sentinel
  where the other holds a real date, on the same rows across all three of
  `hba1c_updated_date`, `fbg_updated_date` and `bmi_date`. That the three
  columns move together points at
  `_extract_date_from_measurement` / R's `extract_date_from_measurement` (the
  legacy path that lifts a date out of the measurement cell's parentheses)
  rather than at nine separate causes. Start there, per tracker, and hand any
  clinical-note share to [ticket 39](39-recover-dates-embedded-in-free-text.md)
  rather than triaging it.
- **`insulin_subtype` (11).** R holds null, Python `Undefined`, in 2025/2026
  Calamba Doctors and 2025 Pahol. These rows tick nothing (`-` in all five
  columns) -- but R publishes `Undefined` for the 17,418 rows whose columns are
  all *null*, so R distinguishes the two cases and Python does not. Find what
  R's derivation does with an all-`-` row and decide whether Python should
  follow.
- **The long tail (~25):** `hba1c_updated` (8), `dob` (7), `fbg_baseline_mg`
  (6), `remote_followup` (2), `testing_frequency` (1), `fbg_baseline_mmol` (1)
  -- including the four `clinic_visit`/`remote_followup` rows the map's **Not
  yet specified** section has carried since ticket 49, which belong with
  whatever round works the tail. `fbg_baseline_mg` is worth a direct look
  first: round 8 wired the FBG text classifiers to that column too, so what is
  left there is a different mechanism.

Split further rather than leaving this open-ended if it does not converge --
eight rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is
wrong, that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.

## Resolution

**Decision.** The nine-column date family is one R mechanism, not nine causes,
and Python is the correct side of all of it. Three classifiers now carry it,
and three Python gaps the same investigation exposed are fixed. The in-scope
cleaned residual goes **448 -> 96 (79%)**; the patient raw stage is
byte-identical at 0 unclassified and product is unchanged.

**The mechanism, executed rather than read.** R's `parse_dates`
(`r-archive/R/script2_helper_patient_data_fix.R`) shortens any word of four or
more letters with `sub("([[:alpha:]]{3})[[:alpha:]]", "\\1", date)`, which
deletes the *fourth* letter and leaves the rest of the word standing, then
hands the wreckage to `lubridate::parse_date_time` with the fixed order list
`c("dmy","dmY","dbY","by","bY","mY","my","y")`. Nothing in that chain can fail
loudly. Installing lubridate and running it over the source strings taken from
the raw parquet reproduced R's frozen output exactly in every case:

- `April-17` becomes `Aprl-17`, no order matches a month, the list falls to
  `y`, and R publishes **2017-01-01**. Same for `August,2015` -> `Augst,2015`
  -> 2015-01-01. That is `r_month_name_truncated_to_year` (88 cells).
- `9-Dce-20` has an unreadable month, so `my` reads the remaining digits as
  month and year and R publishes **2020-09-01** -- the *day* promoted to a
  month, the day itself invented as the 1st. Same for `11-Mach-20` ->
  2020-11-01, `4-Okt-2023` -> 2023-04-01, `10-MAC-2026` -> 2026-10-01. That is
  `r_reads_day_as_month` (143 cells).
- `25-Mach-20` needs month 25, so the whole list misses and R sentinels; so do
  `05/15/2026` and `Dec-22-2025`, month-first spellings no order in the list can
  express. That is `r_parse_order_cannot_read_cell` (107 cells), deliberately
  not applied to `hospitalisation_date`, whose residual round 6 measured as
  100% clinical notes -- R sentinels those because it cannot read a sentence,
  which is [ticket 39](39-recover-dates-embedded-in-free-text.md)'s question
  wearing the same shape.

**Three Python gaps, all real data loss, all fixed.** Python sentinelled 32
distinct source strings a human reads without effort. Verified the way round 6
verified its parser change -- old parser against new over all **5,187** distinct
raw date strings on the 248-tracker set: **32 changed, every one from the
sentinel to a real date, and no already-parsing value changed its reading.**

1. *Month names Python did not know.* `TYPO_REPLACEMENTS` gains `DCE` (a
   transposition) and `UG` (a dropped letter), plus the Bahasa Malaysia
   abbreviations the Malaysian clinics write in a column everyone else writes in
   English -- `Mac`, `Mei`, `Okt` observed, `Ogos` and `Dis` added to complete
   the set. A new `_THAI_MONTH_REPLACEMENTS` covers all twelve Thai
   abbreviations with or without their full stops, for Nakornping's 2025 and
   2026 trackers. These are locale spellings, not typos, and the code says so.
2. *Separator runs damaged by a stray keystroke.* `26-05- 2007`, `19-Jan_2023`,
   `02-Apr=-2026`, `23/05//2025`, `16-July-/2025`, `7_May-21` -- R recovers all
   of these because lubridate splits on any non-alphanumeric run where dateutil
   needs a well-formed separator. `_DAMAGED_SEPARATOR` collapses a run of two or
   more separator characters, or a lone `_`/`=`, to a single `-` on a second
   attempt only. Deliberately narrow: a single `/` or `.` is left alone so no
   already-parsing value changes reading, and a whitespace-only run is left
   alone so the trailing-free-text path still sees its word boundaries.
3. *Invisible characters.* A zero-width space pasted in from another
   application (`11<U+200B> Mar 2026`) is stripped.

**The guard that measurement found, not reasoning.** The first version of the
separator repair turned `11-15 /01/2019` -- a *range* of two visit days -- into
2001-11-15, a date the cell does not hold. The repair now runs only when the
result leaves at most three numbers.

**Rejected.** A general "any run of non-alphanumerics is a separator" rule,
matching lubridate: it is what produced the fabricated 2001-11-15, and it would
also have taken `26/102022` and `10/1023`, where the missing separator's
position is a guess. Fuzzy month matching by edit distance instead of an
explicit spelling list: it would have swallowed `Ma4` silently, which is exactly
the cell nobody can resolve. Classifying the R-sentinel shape on `day > 12`
across *all* date columns: measured first, and it would have mislabelled 79
`hospitalisation_date` clinical notes as this cause -- the reason that column is
excluded by name. What the chosen route gives up: the three classifiers are
shape tests, so they cannot see the source string that proves the mechanism;
the proof lives in this comment and in the executed R runs behind it, not in
the code.

**Deliberately not decided.** `insulin_subtype`'s 11 cells were traced to their
mechanism and left unclassified. R's derivation
(`script2_process_patient_data.R:101`) is a chain of `ifelse(x == "Y", ...)`
pasted together: an all-`-` row yields `""`, which `check_allowed_values` turns
into NA, while an all-null row yields `NA`, which pastes to a string and becomes
`Undefined`. So **R's null-vs-`Undefined` split is NA propagation, not a
designed distinction**, and R's null on these rows is not evidence of intent.
That makes these cells the map's existing fog entry on unticked insulin rows,
reached from the `-` side -- a change to shared behaviour on 17,418 rows, which
round 8 already measured and reverted. Left visible rather than labelled.

**Evidence.** Executed: R's truncation and order list run over the real source
strings under R 4.5 with lubridate installed; the old-vs-new parser sweep over
5,187 distinct raw strings; a full patient pipeline run over the 248-tracker
drive set followed by a full four-stage comparison
(`output/comparison/2026-08-19T212139Z`); 843 tests, ruff, `ty check src/`.
Read: R's `extract_date_from_measurement` and `insulin_subtype` derivation,
whose consequences are described but not executed -- both are round 10's to
confirm.

**Tense.** Every count above is current behaviour measured on the new run, not
a prediction. The 96 remaining are described in [ticket
57](57-triage-patient-cleaned-residual-10.md).
