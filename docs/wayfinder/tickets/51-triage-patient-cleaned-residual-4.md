---
id: 51
title: Triage the residual patient cleaned-stage mismatches (round 4)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-19
claimed_at: 2026-08-19T10:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 50
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches (round
6)](50-triage-patient-raw-residual-6.md), closed, which took the patient **raw**
stage to zero unclassified mismatches. Six rounds of raw-stage triage are
finished; the cleaned stage is what remains of the patient arm.

Rests on the three cleaned-stage rounds already closed -- [round
1](29-triage-patient-cleaned-residual.md) (55,670 -> 16,698), [round
2](37-triage-patient-cleaned-residual-2.md) (16,698 -> 8,259) and [the date
family](38-triage-patient-cleaned-date-family.md) (8,259 -> 6,652) -- and on
their standing conclusions, in particular that `r_numeric_error_sentinel` was
exhaustively verified in round 1 and that the date-absence marker list is now
declared once and shared.

Rests also on the map's standing scoping rule that the current tracker template
is the golden rule, and on the standing bar that a classifier records
understanding, never a verdict by itself.

The residual is **7,967 across 129 files and 27 columns**, measured on run
`output/comparison/2026-08-18T214952Z`, which is the run to triage against.
Note that this is *higher* than round 3 left it: later rounds moved the number
in both directions as classifiers were re-scoped and the tracker set was
refreshed to 254 files, so re-measure rather than reasoning from the history.

## Question

Triage the 7,967, largest shapes first. Re-measure against the baseline run
before working any shape -- every round so far has found at least one stated
shape had already moved.

- **`fbg_updated_mmol` (2,936)** is **not** this ticket's work: it is [ticket
  44](44-triage-cleaned-fbg-r-null-residual.md), still open, and the two must
  not be triaged twice. Exclude it and confirm the exclusion by column before
  starting.
- **The date family (3,278 across seven columns)**: `fbg_updated_date` (940),
  `hba1c_updated_date` (904), `t1d_diagnosis_date` (661), `hospitalisation_date`
  (638), `bmi_date` (135), `recruitment_date` (80), `last_clinic_visit_date`
  (60), `lost_date` (18), `last_remote_followup_date` (9). Round 3 worked this
  family and left it at 1,994 sentinel-stamped cells; whether this is the same
  population re-grown by later changes or a different one is the first thing to
  establish.
- **`t1d_diagnosis_age` (558)** and **`bmi` (22)**: both formula-derived in the
  source, so `excel_formula_error` is the raw-stage cause; what survives
  cleaning is a different question.
- **Blood pressure (491)**: `blood_pressure_dias_mmhg` (289),
  `blood_pressure_sys_mmhg` (202).
- **The long tail (~470)**: `height` (114), `fbg_updated_mg` (113), the two
  screening dates (132), `insulin_subtype` (67), `province` (57), and eleven
  columns in single digits. `province` is worth taking early despite its size:
  the map's **Not yet specified** section already suspects Python's
  `sanitize_str` strips accents from province names (`Kratié` -> `krati`), and
  57 cleaned-stage province mismatches is exactly where that would show.

Split further rather than leaving this open-ended if it does not converge --
three rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.


## Resolution

**Decision.** Three of the four largest shapes in the cleaned-stage residual are
explained, decided and landed as named causes; the rest is split into [round
5](52-triage-patient-cleaned-residual-5.md). Measured on the drive's real
254-tracker set, the in-scope residual (excluding `fbg_updated_mmol`, which is
[ticket 44](44-triage-cleaned-fbg-r-null-residual.md)'s) goes **5,031 -> 2,538**,
and the whole cleaned-stage unclassified count **7,967 -> 5,474**. Final run:
`output/comparison/2026-08-18T222716Z`.

### 1. `r_ymd_first_misparse` -- 1,714 cells, 11 files. Python is right.

R's `parse_date_string` (`r-archive/R/script2_helper_dates.R`) calls
`lubridate::parse_date_time` with `orders = c("ymd", "dmy", "my")`. lubridate
takes the **first** order that parses, and a source string written `D.M.YY`
parses perfectly well as ymd -- `30.1.18` becomes year 30 -> 2030 -- so the
`dmy` order is never reached. R swaps the day and the year on every such cell.

Verified at source, not inferred: 2018 Yangon Children's Hospital writes these
dates as text inside the value cell -- `Jan18!L92` is `10.3 (22.8.17)` and
`Jan18!N92` is `223(30.1.18)` for MM_YC001 -- day-first, matching Python's
2017-08-22 / 2018-01-30 against R's 2022-08-17 / 2030-01-18.

Python is right on three independent grounds: the source strings above; R's
reading putting **1,236 of the 1,714** cells in the *future* relative to the
tracker's own year while Python's puts none there and lands 1,713 within three
years of it; and source days above 12 (`31.5.16` -> R's 2031-05-16) having no
well-formed year-first reading at all.

Columns: `fbg_updated_date` 801, `hba1c_updated_date` 781, `t1d_diagnosis_date`
107, `hospitalisation_date` 23, `bmi_date` 2. Dominated by 2017/2018 Yangon
(1,467) and 2018 Vietnam National Children's Hospital (211).

### 2. `python_rejects_beyond_tracker_year` -- 722 cells, 25 files. Python is right.

Python's `_validate_dates` (`clean/patient.py`) replaces any date past
31 December of `tracker_year` with the 9999-09-09 sentinel and logs an
`invalid_value` error per patient. R has **no** equivalent guard -- grep over
`r-archive/R` finds no future-date or tracker-year bound on any date column --
so R carries the impossible value through unchanged.

The values are genuinely impossible, not merely surprising. 2022 Vietnam
National Children's Hospital writes **every** `Date of T1D Diagnosis` cell in
its Patient List as a 2023 date: `Patient List!G13` = 2023-07-16 for VN_VC001,
born 2013-03, recruited 2017-07. The workbook has patients diagnosed a year
after the tracker was filled in and five years after they were recruited for
having the disease. That is a source defect -- a finding for [ticket
40](40-source-defect-findings-report.md) -- and sentinelling it is the pipeline
recognizing an unusable value, the same verdict `buddhist_era_typo` reached.

**A false claim was found and corrected while doing this**: `_validate_dates`'s
docstring said the guard "matches R pipeline behavior". It does not; it is a
deliberate divergence, and the docstring now says so and says why.

### 3. `r_unicode_sanitizer_rejects_accent` -- 57 cells, 5 files. Python is right.

The two `sanitize_str` implementations were meant to be the same function and
are not. R's (`r-archive/R/script2_sanitize_str.R`) strips `[^[:alnum:]]`,
which under ICU is Unicode-aware, so accented letters survive; Python's
(`clean/validators.py`) strips `[^a-z0-9]` and folds them away. Both sides
sanitize the value *and* the allowed list before matching, so the difference
only shows where a source spelling differs from its canonical form in the
accents alone.

The entire cause is one Vietnamese province across five VNCH trackers: the
source writes `Thái Nguyễn` (tilde on the second e) where
`reference_data/provinces/allowed_provinces.yaml` line 148 has `Thái Nguyên`.
R sanitizes those to `tháinguyễn` vs `tháinguyên`, misses, and stamps the
`"Undefined"` character sentinel; Python sanitizes both to `thinguyn` and
recovers the canonical name. Python is right -- the province is real and the
accent is a typo -- and this is the value-side twin of ticket 49's
`r_non_latin_header_miss`.

**This resolves the standing fog patch** about `sanitize_str` stripping accents
(`Kratié` -> `krati`). Measured, executed: the folding cannot silently merge two
different provinces, because `validate_allowed_values` *raises* on any two
allowed values that sanitize alike, and the 209-entry province list has zero
such collisions. The suspicion was also backwards -- the folding makes Python
more permissive than R, not less, and it recovers data R discards.

**Because.** All three clear the map's two-bar standard: each has a mechanism
traced to the responsible line of R's or Python's own code, and each has an
explicit verdict on which pipeline is right, backed by the source workbook
rather than by the shape of the diff.

**Rejected.**

- *One `python_rejects_unusable_date` cause covering all 1,167 cells where
  Python sentinels and R keeps a date.* Killed because it merges two different
  mechanisms with two different verdicts. Joining those cells back to Python's
  own raw parquet splits them cleanly: **634** hold a genuine Excel date the
  beyond-tracker-year guard then rejected, **533** hold free text Python's
  parser could not read at all (`9-Dce-20`, `25-Ma4-2025`, `4-Okt-2023`,
  `26/102022`, `DKA - Feb-2020`, `admitted to Yangon General Hosp...`), and 33
  did not match a raw row. Lumping them would have been exactly the
  "labelled, not decided" failure ticket 27 had to be reopened for. The
  classifier that shipped is deliberately narrower and keys on the tracker year
  in the row's own sheet name.
- *Teaching Python to recover the typo'd dates (`9-Dce-20` -> 9 Dec 2020).*
  Killed by the map's standing scoping rule: where a divergence traces to a
  human error in the source workbook, the fix is the workbook. R's guess here
  is actively worse than refusing -- it reads `9-Dce-20` as **2020-09-01**,
  dropping the misspelled month and promoting the day into the month slot.
- *Deciding the free-text cases (`DKA - Feb-2020`, `26 Jun (ceton urine high)`)
  in this session.* Killed because that is precisely [ticket
  39](39-recover-dates-embedded-in-free-text.md)'s open question, and answering
  it here would decide a HITL grilling ticket without the human.
- *Working all four named shapes shallowly rather than the date family deeply.*
  Killed at the start of the session, with the user's agreement.

**What this gives up.** 2,538 in-scope cells remain, and `t1d_diagnosis_age`
(558), blood pressure (491), `height` (114) and `fbg_updated_mg` (113) were not
touched at all. The 533 parse-failure cells stay unclassified on purpose,
because part of that population belongs to ticket 39.

**Evidence.** `executed` throughout: `duckdb` over the exported
`cell_mismatches` sheet for every count; `openpyxl` reads of the real source
workbooks (2018 Yangon, 2022 VNCH) for the source strings; a `polars` join of
the sentinelled cells back to `patient_data_raw` for the 634/533/33 split; a
run of `load_canonical_provinces` + `sanitize_str` for the zero-collision
check; `rg` over `r-archive/R` for R's missing future-date guard; and a full
re-run of `scripts/compare_outputs.py` against the drive for the before/after.
Test suite: 776 passed, 1 skipped; ruff clean.

**Tense.** Every count above is current behaviour of the code as committed in
this session, measured on run `2026-08-18T222716Z`. The 634/533 split is a
measurement of the *previous* run's population, made to justify scoping the new
classifier -- the shipped classifier's own count is 722, which is that 634 plus
the cells in columns the join could not reach.
