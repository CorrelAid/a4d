---
id: 55
title: Triage the residual patient cleaned-stage mismatches (round 8)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-19e
claimed_at: 2026-08-19T23:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 54
---

## Premise

Rests on [round 7](54-triage-patient-cleaned-residual-7.md), closed, which took
the cleaned-stage in-scope residual from 1,200 to **770** and settles two things
this ticket must not re-open:

- **R never derives a diagnosis age at all** -- `fix_t1d_diagnosis_age`'s call
  site is commented out (`script2_process_patient_data.R:251`). The whole
  `t1d_diagnosis_age` column is decided; do not re-triage it.
- **The cleaned stage now numeric-normalizes its string-typed columns**
  (`string_numeric_normalize_targets`, `ALL_STRING_COLUMNS`). A float-rounding
  difference on a string-typed measurement column is no longer a mismatch. If
  one reappears, the harness broke -- do not classify it.

Rests on the seven cleaned-stage rounds before it
([1](29-triage-patient-cleaned-residual.md),
[2](37-triage-patient-cleaned-residual-2.md), [the date
family](38-triage-patient-cleaned-date-family.md), [round
4](51-triage-patient-cleaned-residual-4.md), [round
5](52-triage-patient-cleaned-residual-5.md), [round
6](53-triage-patient-cleaned-residual-6.md), [round
7](54-triage-patient-cleaned-residual-7.md)); on [ticket
42](42-fbg-unit-headers-and-implausible-values.md), which set the analytical
bounds on all four FBG columns and owns the medical-limits question; on the
map's rule that the current tracker template is the golden rule; and on the
standing bar that a classifier records understanding, never a verdict by
itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **770** in-scope cells left on run
`output/comparison/2026-08-19T195625Z`, excluding `fbg_updated_mmol` ([ticket
44](44-triage-cleaned-fbg-r-null-residual.md)) and `hospitalisation_date`
([ticket 39](39-recover-dates-embedded-in-free-text.md)). Re-measure before
working any shape.

Round 7 measured every shape below far enough to name a mechanism but did not
decide any of them. **Two look like real Python defects and should be taken
first** -- per the map's bar, where Python is losing or corrupting information
the pipeline gets fixed, not labelled.

- **`height` (114) -- likely a real Python gap.** The source cells hold `6.9`,
  `2.52`, `2.43`, `2.72`, `13.0` (2025/2026 Señor Sto. Niño, 2021-2023 Likas,
  2019 Mahosot). R sentinels every one of them (999999); Python divides by 100
  and emits `0.069`, `0.0252` metres into production output. Whatever the
  source values mean, Python's are not heights. Find R's own height range
  check, decide whether Python needs the equivalent guard, and settle whether
  the source values are a unit the pipeline should recognize or a source defect
  for [ticket 40](40-source-defect-findings-report.md). Check whether these
  rows also feed `bmi` (see below) before deciding either.

- **`fbg_updated_mg` (113) -- two opposite directions, one of them alarming.**
  85 cells where R produces a plain number and Python sentinels: the source
  reads `Lost follow up` (41 cells, R produces **140**), `SMBG 50-HI`,
  `129-HI`, `CBG 57-High`, bare `HI` (R produces **200**). R's `fix_fbg` is
  manufacturing readings from text -- read it and decide whether 200-for-HI is
  a documented clinical convention worth adopting or an invention, and whether
  140-from-"Lost follow up" is anything but garbage. The other direction (~28
  cells) is the reverse and looks like Python winning: the source reads
  `148 mg/dl   (Mar-18)` and Python extracts 148 where R sentinels.

- **`bmi` (22).** R sentinels, Python computes 10-12. Formula-derived in the
  source, so `excel_formula_error` is the raw-stage cause; what survives
  cleaning is a different question. Decide together with `height` -- a BMI
  computed from an implausible height is not a BMI.

- **`insulin_subtype` (67).** R null, Python `Undefined` on every one -- 56 in
  2024 Sarawak, the rest in 2025/2026 Calamba Doctors and 2025 Pahol. The
  source rows carry real brands (`Novorapid` with `Glargine`, `Toujeo`,
  `Ryzodeg`), so Python's derivation runs and its allowed-values validator then
  rejects the result. Decide whether the allowed-value config is missing
  entries -- which would make this a real Python data loss -- or whether the
  subtype genuinely is undefined for these combinations. Note both pipelines
  lose here; R just loses silently.

- **The smaller date columns** -- `hba1c_updated_date` (108),
  `fbg_updated_date` (101), `bmi_date` (88), `recruitment_date` (58),
  `last_clinic_visit_date` (41), `lost_date` (18), `t1d_diagnosis_date` (12),
  `dob` (7), `last_remote_followup_date` (3). Still unmeasured. Round 6
  established that `hospitalisation_date` is *all* clinical notes; whether the
  same holds here is unknown. Split each by direction (Python sentinels / R
  sentinels / both real and differing) before deciding, and hand any
  clinical-note share to ticket 39 rather than triaging it.

- **The long tail (~30):** `hba1c_updated` (8), `fbg_baseline_mg` (6),
  `remote_followup` (2), `testing_frequency` (1), `fbg_baseline_mmol` (1) and
  the columns in single digits -- including the four
  `clinic_visit`/`remote_followup` rows the map's **Not yet specified** section
  has carried since ticket 49, which belong with whatever round works the tail.

Split further rather than leaving this open-ended if it does not converge --
seven rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.

## Resolution

**Decision.** The in-scope cleaned-stage residual went **770 -> 448** (42%) and
the raw stage held at 0 unclassified. Both suspected Python defects at the head
of the queue were real and are fixed; a third, unsuspected one was found in the
date family; the alarming-looking FBG column turned out to be R manufacturing
readings, with no Python defect at all.

**`height` (114 -> 0) and `bmi` (22 -> 0): one Python defect with two halves,
both live in production output.** `_apply_range_validation` (clean/patient.py)
converted a height to metres whenever it exceeded **2.3**, where R's
`transform_cm_to_m` converts only above **50**. A source value between the two
is neither unit -- the affected cells hold `2.31`, `2.37`, `2.43`, `2.52`,
`2.56`, `2.70`, `2.72`, `2.82`, `6.9`, `10.4`, `13.0` (120 cells, measured over
the whole raw output) -- so R divides nothing, the value fails the [0, 2.3]
bound and becomes the sentinel, while Python divided by 100 and published
`0.069`, `0.0243`, `0.13` metres. The threshold is now 50, which makes an
unusable cell sentinel instead of turning it into a plausible-looking metre
reading. The 2025 Señor Sto. Niño tracker records metres throughout
(1.52-1.73), so these are source defects for [ticket
40](40-source-defect-findings-report.md), not a third unit.

The second half is ordering. R computes `fix_bmi` *after* cutting height, so an
out-of-bounds height propagates its sentinel into the BMI; Python computed BMI
at step 5.7, before range validation, from the raw height -- `60 / 2.43^2` =
10.16, which then passed the [10, 80] BMI bound and reached production as a
real-looking BMI derived from an impossible height. The BMI derivation now runs
inside `_apply_range_validation`, after the height and weight cuts and before
the BMI cut, exactly as R sequences it.

**`fbg_updated_mg` (113 -> 0): no Python defect -- R manufactures glucose
readings from text.** All 85 cells where R holds a number and Python sentinels
were joined back to their raw source. `fix_fbg`
(r-archive/R/script2_helper_patient_data_fix.R:551) runs its CDC category
patterns through `grepl` on the whole string with no word boundary:

- 41 cells read **`Lost follow up`** and become **140**, because "fol-low"
  contains "low". A patient lost to follow-up has no reading at all, and R
  publishes a fasting glucose for them.
- 41 cells record a meter range or an out-of-range marker -- `SMBG 50-HI`,
  `DSMP 250-HI`, `129-HI`, `CBG 57-High`, `112/ High`, bare `HI` -- and all
  become **200**, discarding the numeric endpoint the clinic wrote. On a
  glucometer "HI" means a reading above the analytical ceiling, far above 200,
  so the substitution is wrong in direction as well as invented.
- 3 are a genuine `low`/`Low`, R's rule working as designed.

Python diverges here **by design and was already correct**: `_fix_fbg_column`
implements the same CDC mapping but anchors each pattern to the full string
(`^(low|good|okay)$`), so only a cell that says exactly "low" is a category and
everything else sentinels. The opposite direction (28 cells) is Python winning
outright: the 2018 trackers write `148 mg/dl   (Mar-18)`, and Python strips the
unit and lifts the date into `fbg_updated_date` while R's `as.numeric` fails on
the whole string. Two classifiers, `r_fbg_text_category_invention` and
`r_unit_suffix_not_stripped`, both scoped to the two mg/dL columns `fix_fbg`
runs over.

**`insulin_subtype` (67 -> 11): a real Python data loss, recovered.** 2024
Sarawak General ticks the template's five insulin tick boxes by writing the
drug's name -- `Novorapid` in the rapid-acting column, `Glargine`, `Toujeo` or
`Ryzodeg` in the long-acting one. Both pipelines tested for `Y` exactly, so
both discarded the subtype, and Python's empty derivation was then published as
`Undefined` for 56 rows. `_insulin_ticked` (clean/patient.py) now reads any
value that is not a negative marker as a tick, and those rows carry
`Rapid-acting,Long-acting`. The negative set is enumerated rather than inferred
because the vocabulary is closed and tiny: across all 248 trackers these five
columns hold only `Y` (39,775), `-` (68,001), `0` (4), the four drug names
(116) and null. Classifier `r_drops_drug_name_tick`.

**A third Python defect, found in the date family and fixed:
`parse_date_flexible` accepted a year with a digit missing.** 2024 Vietnam
National Children's writes `1/16/224` and `5/16/223`, 2023 Yangon General
writes `13-Mar-0202`, and other cells read `31 oct 222` and `1-Oct-205`.
dateutil reads each literally, so Python published `0224-01-16`, `0202-03-13`,
`0205-10-01` into production output -- 24 cells across six date columns. The
cleaned stage's future-date guard only bounds the calendar at one end;
`_MIN_PLAUSIBLE_YEAR = 1900` now bounds the other, in the parser so every route
into it is covered, and such a cell sentinels as unreadable.

**What is left (448 in scope) and why it is not this session's.** The nine
smaller date columns still hold 412 cells, and measuring them by direction
showed the shape the ticket expected is not there: only 2 of 414 are a
day/month swap, none is a year-only difference, and the residual is a mix of
per-tracker populations (2021 and 2020 Mahosot DC alone account for ~150, with
R and Python each sentinelling where the other holds a real date). That is a
round of its own, and became [round 9](56-triage-patient-cleaned-residual-9.md)
together with the 11 remaining `insulin_subtype` cells and the ~25-cell tail.

**Rejected.**
- *Adopting R's `HI` -> 200 convention.* It is not a clinical convention but a
  CDC page about diagnostic thresholds; a meter reporting "HI" is above its
  measuring range, so 200 understates a critical hyperglycaemia. Python's
  sentinel is the honest reading and the source cell is a ticket 40 finding.
- *Extracting the numeric endpoint from `SMBG 50-HI` or `129-HI`.* These are
  ranges over a month, not single readings; choosing either endpoint is a
  guess, and the map's bar treats a guess as worse than a refusal.
- *Publishing null instead of `Undefined` for an insulin row with no tick.*
  Tried and reverted after measuring: R publishes `Undefined` on 17,418 such
  rows and Python already agreed with it there, so the change created 17,418
  new divergences while resolving none. Whether `Undefined` should claim a
  subtype the clinic never recorded is a real question -- recorded as fog on
  the map, in the same family as the numeric absence-as-word patch, not
  smuggled into a triage round.
- *Treating the between-units heights as a third unit (feet, say).* 2.43 feet
  is 74cm and 6.9 feet is 2.10m; no single interpretation fits the set, and the
  tracker that holds most of them records metres correctly on every other row.
- *A tick rule of "anything that is not `Y` or `-`".* Would have read `0` as a
  tick. The negative markers are enumerated instead.

**Evidence.** Executed. R's `fix_fbg`, `transform_cm_to_m`, `cut_numeric_value`
and the `script2_process_patient_data.R` mutate that sequences them read
directly from `r-archive/`; every mismatch population joined back to Python's
own raw stage to recover the source strings; the parser's behaviour on the
truncated-year strings reproduced by calling `parse_date_flexible` directly.
Measured across three full pipeline runs and four comparison runs over the real
248-tracker drive data (`2026-08-19T195625Z` before, `2026-08-19T204438Z` the
reverted insulin attempt, `2026-08-19T204927Z` after the fixes,
`2026-08-19T205332Z` after the classifiers). Full suite 816 passed / 1 skipped,
ruff and `ty check src/` clean.

**Tense.** Every count is current behaviour of the code as committed, measured
on run `2026-08-19T205332Z`. The `0.069`-metre and `0224-01-16` values
described as reaching production were doing so before this session's fixes.
