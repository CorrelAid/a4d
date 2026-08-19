---
id: 52
title: Triage the residual patient cleaned-stage mismatches (round 5)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-19b
claimed_at: 2026-08-19T14:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 51
---

## Premise

Rests on [round 4](51-triage-patient-cleaned-residual-4.md), closed, which took
the cleaned-stage in-scope residual from 5,031 to **2,538** by landing three
causes: `r_ymd_first_misparse` (1,714), `python_rejects_beyond_tracker_year`
(722) and `r_unicode_sanitizer_rejects_accent` (57). Read its resolution before
starting -- it decides three things this ticket must not re-open:

- **R's date parsing is year-first and wrong**, so any further date divergence
  should be checked against `r_ymd_first_misparse` before being called new.
- **Python's beyond-tracker-year guard is a deliberate divergence from R**, not
  a parity gap, and `_validate_dates`'s docstring now says so.
- **Python's ASCII-folding `sanitize_str` is safe on allowed-value columns**,
  because `validate_allowed_values` raises on any two allowed values that
  sanitize alike. Do not re-argue the accent question.

Rests on the four cleaned-stage rounds before it ([1](29-triage-patient-cleaned-residual.md),
[2](37-triage-patient-cleaned-residual-2.md), [the date
family](38-triage-patient-cleaned-date-family.md), [round
4](51-triage-patient-cleaned-residual-4.md)) and on the map's standing scoping
rule that the current tracker template is the golden rule, and on the standing
bar that a classifier records understanding, never a verdict by itself.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **2,538** in-scope cells left on run
`output/comparison/2026-08-18T222716Z`. Re-measure before working any shape;
every round so far has found at least one stated shape had already moved.

`fbg_updated_mmol` (2,936) is **not** this ticket's work -- it is [ticket
44](44-triage-cleaned-fbg-r-null-residual.md). Exclude it and confirm the
exclusion by column before starting.

- **`t1d_diagnosis_age` (558)** and **`height` (114)**, **`bmi` (22)** --
  untouched by round 4. `t1d_diagnosis_age` is formula-derived in the source,
  so `excel_formula_error` is the raw-stage cause; what survives cleaning is a
  different question. Largest single shape in scope: take it first.
- **The parse-failure date cells (~533 measured in round 4, spread across
  `hospitalisation_date` 546, `hba1c_updated_date` 108, `fbg_updated_date` 103,
  `bmi_date` 94, `recruitment_date` 72, `last_clinic_visit_date` 41, and a
  small tail).** Round 4 measured this population by joining the sentinelled
  cells back to `patient_data_raw`: Python stamps the date sentinel on a cell
  it could not parse at all, and R guesses -- badly, reading `9-Dce-20` as
  2020-09-01. It splits into two kinds, and **only the first is takeable here**:
  - *A mangled date token and nothing else* (`9-Dce-20` 81 cells,
    `25-Ma4-2025` 18, `4-Okt-2023` 3, `26/102022` 5, `19-Jan_2023` 5). Round 4's
    verdict, if it holds on re-measurement, is that Python is right to refuse
    and the workbook is what needs correcting -- a [ticket
    40](40-source-defect-findings-report.md) finding.
  - *A date buried in a clinical note* (`DKA - Feb-2020` 20,
    `26 Jun (ceton urine high)` 30, `DKA; Jul 2018` 12, `admitted to Yangon
    General Hosp...`). This is [ticket
    39](39-recover-dates-embedded-in-free-text.md)'s open HITL question. Do not
    decide it here; measure it and leave it.
- **Blood pressure (491)**: `blood_pressure_dias_mmhg` (289),
  `blood_pressure_sys_mmhg` (202). Note these columns already carry
  `r_extraction_gap` for the 2026 template's Annual sheet, so the residual is
  something else.
- **The long tail (~370)**: `fbg_updated_mg` (113),
  `complication_screening_lipid_profile_cholesterol_value` (72),
  `insulin_subtype` (67), `complication_screening_kidney_test_value` (60),
  `lost_date` (18), and nine columns in single digits.

Split further rather than leaving this open-ended if it does not converge --
four rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is wrong,
that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.


## Resolution

**Decision.** The largest in-scope shape, `t1d_diagnosis_age`, is explained and
decided, and it turned out to be two real Python bugs rather than a labelling
job. The in-scope cleaned residual goes **2,538 -> 2,278**; the rest is split
into [round 6](53-triage-patient-cleaned-residual-6.md). Final run:
`output/comparison/2026-08-19T174047Z`.

### 1. A bare four-digit year in a date cell became a 1905 date. Python was wrong; fixed.

Nine trackers type a year alone where the template's own subheading asks for
`(dd-mmm-yyyy)`. `parse_date_flexible` read `2011` as an Excel serial, which
lands on 1905-07-03, and the damage showed downstream: `t1d_diagnosis_age`
came out **-95, -97, -101** (1905 minus the birth year) on 239 cells, and
`age` hit the 999999 sentinel for every patient with a bare birth year.

Two code paths had to change, because the misreading happens at two different
places depending on one cell format:

- `BARE_YEAR_MIN`/`BARE_YEAR_MAX` (`clean/date_parser.py`): a whole number in
  1900-2100 is now read as that year, resolved to 1 January. As a serial the
  same number means 1905, which no tracker records anything from, so the two
  readings cannot collide.
- `_IMPOSSIBLE_DATE_BEFORE` raised 1903 -> 1906 (`extract/patient.py`),
  extending ticket 46's rule. Where the cell is *date*-formatted, openpyxl
  resolves the number before cleaning ever sees it; those serials land in
  March-September 1905 and so escaped the old bound. 2019 Yangon Children's
  is the only file in the set that formats the column this way -- its 2017,
  2018 and 2020 siblings leave it General -- which is why this half stayed
  invisible until the parser fix made the two sides disagree.

**Python is right, and the source says so rather than the shape of the diff.**
Sarawak General Hospital's **2024** workbook writes the same patients'
diagnoses as real 1-January dates (`Patient List!G10` is 2011-01-01 for
MY_SW001, read with openpyxl) where its 2025 and 2026 workbooks write the bare
year, so the first of January is the clinic's own convention for a year with
no day, and the recovered ages agree across the three years (MY_SW001: 10 in
both; MY_SW003: 1 in both). R has every such patient born or diagnosed in
1905.

Scale: 590 `dob` cells across four Yangon Children's trackers and 425
`t1d_diagnosis_date` cells across Sarawak, Uni Med Center, VNCH, Heart of
Jesus and MMMHMC. After the fix, the whole cleaned output holds **zero**
birth dates before 1930, down from 590.

### 2. `t1d_diagnosis_age` went negative where the source contradicts itself. Python was wrong; fixed.

2023 Likas records MY_LW004 as born 2016-08-17 and diagnosed 2015-05-29 --
diagnosed a year before birth -- and the workbook's *own* age formula resolves
to `#NUM!`. `_fix_t1d_diagnosis_age` (`clean/patient.py`) derived anyway and
emitted -2. It now returns null when the derivation goes negative: the two
dates contradict each other, so the arithmetic has nothing to say about the
row. 25 cells across 2023 Likas (12), 2023 Yangon General (10) and 2024
Putrajaya (3). The source workbooks are what need correcting -- a [ticket
40](40-source-defect-findings-report.md) finding. The whole cleaned output now
holds zero negative diagnosis ages.

### 3. Two classifiers, both keyed on mechanism rather than shape.

- `python_reads_bare_year` (1,166 cells) requires R's date to be *exactly* the
  Excel serial of the year Python read, which no coincidentally-1-January date
  can satisfy.
- `python_age_from_bare_year` (992 cells) covers `age` and
  `t1d_diagnosis_age` derived from such a date. It needed a new row-level
  flag, `row_has_bare_year_date`, set by `compare_cells` across the whole row
  -- the same opt-in-diagnostic pattern as `row_order_candidate` (ticket 21).
  The derived values' shape alone (R at the 999999 sentinel, Python plausible)
  cannot be told apart from a genuine age disagreement, and 590 of 597 `age`
  mismatches sit on a row that itself carries a bare-year date, measured
  rather than assumed.

**Because.** Both fixes clear the map's two-bar standard: each has a mechanism
traced to the responsible line of Python's own code, and each has a verdict
backed by the source workbook -- the cross-year Sarawak comparison for the
bare year, Excel's own `#NUM!` for the negative ages.

**Rejected.**

- *Treating the bare year as a source defect to report rather than recover*
  (the map's standing "fix the workbook, not the pipeline" rule). Killed by
  the cross-year evidence: the same clinic writes 2011-01-01 explicitly in one
  year and `2011` in the next, so recovering the year reproduces what the
  clinic itself wrote rather than guessing at it -- and the parser already
  accepts reduced precision one notch finer (`Jun 2006` -> 2006-06-01, ticket
  37). Refusing would have left 590 birth years and 425 diagnosis dates as
  1905 in production BigQuery, which is not a neutral outcome.
- *Fixing only `parse_date_flexible`.* Killed on measurement: it left 2019
  Yangon Children's unfixed and produced a **163-cell regression at the raw
  stage** where six earlier rounds had reached zero. That regression was the
  signal that found the extraction half; it is resolved, and the raw stage is
  back to 0 unclassified.
- *Sentinelling the negative ages with 999999 rather than nulling them.* Would
  match R, but 999999 claims "a value was recorded and is invalid"; nothing
  was recorded here, and ticket 29 already settled that null is the right
  claim for that case.
- *Adding a `t1d_diagnosis_age` range bound to `validation_rules.yaml`.*
  Killed as the wrong layer: the bound would fire on a value the derivation
  should never have produced, and `patient.py`'s ranges are a golden file the
  YAML only mirrors.
- *Working the other named shapes shallowly.* `hospitalisation_date` (546),
  blood pressure (491), `height` (114) and `fbg_updated_mg` (113) are
  untouched, deliberately -- see round 6.

**What this gives up.** 2,278 in-scope cells remain and most of the ticket's
named shapes were not reached. The parse-failure date cells stay unclassified
on purpose, because part of that population belongs to [ticket
39](39-recover-dates-embedded-in-free-text.md).

**Evidence.** `executed` throughout: `duckdb` over the exported
`cell_mismatches` sheets for every count; `openpyxl` reads of the real source
workbooks (2024/2025 Sarawak, 2019 Yangon, 2023 Likas) for the cell values and
number formats; `polars` joins of the flagged cells back to
`patient_data_raw`; a row-level join proving 590/597 `age` mismatches sit on a
bare-year row; and two full re-runs of the patient pipeline plus
`scripts/compare_outputs.py` against the drive's 254-tracker set for the
before/after. Test suite: 785 passed, 1 skipped; ruff and `ty check src/`
clean.

**Tense.** Every count is current behaviour of the code as committed in this
session, measured on run `2026-08-19T174047Z`. The 2,538 starting figure is
round 4's closing measurement, re-verified at the start of this session.
