---
id: 57
title: Triage the residual patient cleaned-stage mismatches (round 10)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-20
claimed_at: 2026-08-20T10:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 56
---

## Premise

Rests on [round 9](56-triage-patient-cleaned-residual-9.md), closed, which took
the in-scope cleaned residual from 448 to **96** and settles three things this
ticket must not re-open:

- **R's `parse_dates` is understood end to end**, and it is one mechanism, not
  nine. It deletes the fourth letter of any 4+ letter word, then walks
  `c("dmy","dmY","dbY","by","bY","mY","my","y")` over whatever digits remain --
  so a spelled-out month becomes 1 January of its year, an unreadable month
  makes R read the *day* as the month, and a day past 12 leaves R with no
  reading at all. Executed against R 4.5, not read. The three classifiers
  `r_month_name_truncated_to_year`, `r_reads_day_as_month` and
  `r_parse_order_cannot_read_cell` carry it, and Python is the correct side of
  all three.
- **Malay and Thai month names, "Dce" and "ug" now parse.** `TYPO_REPLACEMENTS`
  and `_THAI_MONTH_REPLACEMENTS` (clean/date_parser.py) map them before
  parsing. If one reappears, a fix regressed.
- **A separator run damaged by a stray keystroke is repaired** -- but only when
  the repair leaves at most three numbers, so a date range is never collapsed
  into one date.

Rests on the nine cleaned-stage rounds before it, on the map's rule that the
current tracker template is the golden rule, on the standing bar that a
classifier records understanding and never a verdict by itself, and on
[ticket 42](42-fbg-unit-headers-and-implausible-values.md) for the FBG
analytical bounds.

Would be void, not merely rewritten, if the destination stopped requiring every
R/Python difference to be explained before R is retired.

## Question

Triage the **96** in-scope cells left on run
`output/comparison/2026-08-19T212139Z`, excluding `fbg_updated_mmol` ([ticket
44](44-triage-cleaned-fbg-r-null-residual.md)) and `hospitalisation_date`
([ticket 39](39-recover-dates-embedded-in-free-text.md)). Re-measure before
working any shape. Five groups, and unlike earlier rounds they share no
mechanism:

- **The 2017/2018 measurement-cell dates (~27).** `fbg_updated_date` and
  `hba1c_updated_date` where R holds the first of a month and Python holds
  null or the sentinel, in 2017/2018 Mandalay, Penang DC, CDA and Mahosot.
  These trackers have **no date column at all** in Python's raw output: R's
  `extract_date_from_measurement` (script2_helper_patient_data_fix.R) splits a
  measurement cell written `8.53 (28/8/2017)` into a value and a date, and
  Python never does this for those years. This is the legacy path round 9 was
  sent looking for and did not find in the Mahosot DC concentration -- it lives
  here instead. **Decide whether Python should extract it too**; if so, this is
  a pipeline fix, not a classifier.
- **`25-Ma4-2025` (18), one cell in 2025 Taunggyi.** "Ma4" is Mar or May and
  nothing in the workbook says which; R reads the digits positionally and
  publishes 2025-04-25, a third answer neither spelling supports. The row's
  `status` is `Active` while carrying a `lost_date` at all. Most likely a
  finding for [ticket 40](40-source-defect-findings-report.md) rather than
  something to infer -- say so explicitly rather than labelling it.
- **Glued or stray digit groups (~19).** `26/102022`, `8/1023`, `10/1023`,
  `3/10.23`, `10-Oct-2-24`, `13-Mar-0202`. Where the missing separator goes is
  a guess, and R's own answer is not stable: R's frozen output has
  `10/1023` as 2010-10-23 while running R's `parse_dates` over that string in
  isolation returns 2023-10-10. Decide whether any of these are recoverable at
  all, or whether they are source defects.
- **The numeric tail (14).** `hba1c_updated` 240, 299 and 125, and
  `fbg_baseline_mg` 47.8 and 53.8, where R publishes the number and Python
  stamps 999999; plus one `fbg_baseline_mmol` and one `testing_frequency`
  holding a date. The hba1c values look like a glucose reading typed into the
  HbA1c column, but the FBG pair sits inside the mg/dL analytical bounds and
  should not have been rejected -- **check why Python sentinels it before
  assuming Python is right.**
- **`Undefined` on a row that ticks nothing (13).** `insulin_subtype` (11) and
  `remote_followup` (2). Round 9 established the mechanism and deliberately did
  not fix it: R's `ifelse(x == "Y", ...)` chain yields `""` for an all-`-` row,
  which `check_allowed_values` turns into NA, and `NA` for an all-null row,
  which becomes `Undefined`. R's null-vs-`Undefined` split is NA propagation,
  not a designed distinction, so R's null here is not evidence of intent. These
  cells are the **Not yet specified** fog entry on unticked insulin rows
  reached from the `-` side, and they stay unclassified until that question is
  answered. Confirm `remote_followup` is the same shape; do not decide the fog.

Split further rather than leaving this open-ended if it does not converge --
nine rounds have already split rather than sprawled.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining a
difference and naming a cause is not enough -- each needs an explicit verdict on
whether Python is right, with the evidence. Where Python is losing information
the source carried, fix the pipeline. Where the source workbook itself is
wrong, that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on the
available evidence is recorded as an open question, not closed with a label.

## Resolution (session-2026-08-20)

**Decision.** The in-scope cleaned residual falls **96 -> 19** (80%), the raw
stage is byte-identical at 26,172 and product is untouched. Every one of the 19
carries a written verdict: 13 are the standing `Undefined` fog and 6 are a
tooling limitation named below. **There is no round 11** -- this closes the
ten-round patient cleaned-stage chain.

One pipeline fix, four classifiers, and a verdict on each of the five groups.

**The measurement-cell group was a real Python defect, and this ticket's
premise about it was wrong.** The premise said Python "never does this for
those years". It does: `_extract_date_from_measurement`
(`src/a4d/clean/patient.py`) is a documented port of R's function and has been
called from `_apply_legacy_fixes` all along. The defect was one character.
R's `separate_wider_regex` makes the closing parenthesis **optional**
(`[)]?`, `script2_helper_patient_data_fix.R:124`) and R's own test suite
covers an unclosed cell (`"10.75 (01-Sept-2022"`,
`test-helper_patient_data_fix.R:229`). Python's `\(([^)]+)\)` required the
closer -- and the 2017/2018 Mandalay, CDA, Mahosot and Penang DC trackers
write `180(May-2017`, `201(Jun-2017`, `8.4(Jan-2018` and never close it.
25 of the 30 cells in this group had no closing parenthesis at all.
Python now uses R's shape: greedy prefix, date after the **last** `(`,
optional closer. **24 cells recovered**, and the dates are right -- MM_MD022's
Dec17 row now publishes `fbg_updated_mg = 180`, `fbg_updated_date =
2017-05-01`, matching R and the source cell.

**Matching R exactly would have destroyed data, and the measurement caught
it.** R's greedy prefix leaves `196(` as the *value* for `196((Dec-2017)`, and
R's own `as.numeric` then fails on it -- R loses the reading of 196. The first
version of this fix reproduced that faithfully, which made the comparison count
*drop by two* because both sides were now equally wrong. Python strips the
stray `(` and keeps 196. This is a deliberate divergence from R, in the
direction the map's standing bar requires.

**The two FBG cells this ticket flagged as wrongly sentinelled are correctly
sentinelled.** The ticket's suspicion was that 47.8 and 53.8 "sit inside the
mg/dL analytical bounds and should not have been rejected". Measured: 2020
Kantha Bopha's `fbg_baseline_mg` is 382 of 424 non-null readings below 30 --
**90.1%**, just over ticket 42's 90% threshold -- so `resolve_glucose_units`
reads the whole column as mmol/L, and 47.8 mmol/L is past the analytical
ceiling. They are not mg/dL readings, so the mg/dL bounds never applied. The
verdict rests on the ticket-42 assumption in force, and 90.1% is close enough
to the threshold that both cells are reported for source correction rather than
called settled.

**The other three groups: R invents, Python declines, and the source is the
defect.** `25-Ma4-2025` (18 cells), the glued digit groups (19) and the 2018
Penang DC template placeholder `e.g. xxx (mth-18)` (6) are one story told
three ways. Round 9 established by running R 4.5 that `parse_dates` cannot fail
quietly, so R always publishes *something*; where the source token is damaged
past reading, that something is an invention, and R's own answer is not even
stable (`10/1023` is 2010-10-23 in R's frozen output and 2023-10-10 when R's
parser is run over that string in isolation). Python declining is correct, and
all 37 cells are workbook fixes -- appended to [ticket
40](40-source-defect-findings-report.md).

**Because.** Every verdict here was measured rather than argued: the source
value behind all 96 cells was joined back from Python's raw parquet, the
parenthesis shapes counted (25 unclosed of 30), the swap threshold recomputed
against the real column, and the whole patient arm re-run and re-compared twice
against the real 254-tracker drive data.

**Rejected.**

- *Making Python match R byte-for-byte on `196((Dec-2017)`.* Rejected because R
  loses the reading. Costs a permanent 2-cell divergence in `fbg_updated_mg`
  and `fbg_updated_mmol`, which is the right trade.
- *Widening `_is_python_glucose_unit_corrected` to "outside either unit's
  range" so it would catch the six Kantha Bopha cells.* Written, measured
  against the test suite, and **backed out**: it would also claim every
  genuinely-rejected mg/dL reading between 45 and 800 as a unit correction.
  Whether a column was swapped is a property of the column; a per-cell
  classifier cannot see it. The six stay `unclassified` with the reason
  recorded, which the map's bar explicitly permits, rather than wearing a label
  that would be wrong for most of the population it could match.
- *Inferring a date for `25-Ma4-2025` or the glued digit groups.* Rejected:
  nothing in the workbook decides between Mar and May, and R's instability on
  `10/1023` shows its number is not evidence either.
- *Deciding the `Undefined`-on-an-unticked-row question (13 cells).* Out of
  scope by round 8's measurement -- changing it created 17,418 new divergences.
  Confirmed this round that `remote_followup` (2) is the same shape as
  `insulin_subtype` (11): both source cells are empty, R holds null, Python
  holds `Undefined`. Left to the fog entry.

**Evidence: executed.** The pipeline fix, the parenthesis counts, the 90.1%
swap threshold, the recovered values and the 96 -> 19 movement were all run
against the real drive data, not read. R's optional `[)]?` and its unit test
were **read** from `r-archive/` source, not re-executed -- but the behaviour
they predict is confirmed by R's frozen output on those same cells. 860 tests,
ruff and `ty check src/` all pass.

**Tense.** The 96 -> 19 figure, the recovered dates and the 19-cell residual
describe current behaviour after this session's change, verified on run
`output/comparison/2026-08-20T074301Z`. Nothing here is a proposal.

### What was added

- `_extract_date_from_measurement` (`src/a4d/clean/patient.py`) -- R's regex
  shape, minus R's stray-`(` data loss. 5 unit tests.
- `python_declines_unreconstructable_date` -- R on a real date, Python on the
  sentinel. Wired to every schema-derived date column except
  `hospitalisation_date` (ticket 39's, same carve-out round 9 made), and
  appended last so it only ever sees what nothing narrower claimed. 37 cells.
- `python_rejects_out_of_range_hba1c` -- a fasting-glucose reading typed into
  the HbA1c column, rejected against the bound read from
  `validation_rules.yaml` rather than restated. 8 cells.
- `stray_date_dropped` -- the third face of ticket 24's stray-date cause, for
  an integer-typed column where Python's failed cast leaves null rather than 0.
  1 cell.
- `python_recovers_glucose_r_rejected` -- the unit swap moving across a reading
  R had already sentinelled. 1 cell.
