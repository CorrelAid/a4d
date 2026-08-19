---
id: 57
title: Triage the residual patient cleaned-stage mismatches (round 10)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 56
---

## Premise

Rests on [round 9](56-triage-patient-cleaned-residual-9.md), closed, which took
the in-scope cleaned residual from 448 to **94** and settles three things this
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

Triage the **94** in-scope cells left on run
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
