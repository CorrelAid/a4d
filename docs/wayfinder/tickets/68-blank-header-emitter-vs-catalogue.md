---
id: 68
title: The pipeline reports 217 headerless-column defects where the triage found 4,572
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-27
claimed_at: 2026-08-27
resolution: decided
evidence: executed
closed_by: null
spawned_by: 16
---


> **Code names below are superseded (2026-08-26)**, but this ticket's headline
> numbers are not. [The finding taxonomy
> rework](69-miscategorised-and-duplicated-findings.md) left
> `blank_header_with_data` at **217 across 24 trackers**, unchanged, so the
> 217-vs-4,572 discrepancy this ticket exists for still stands exactly as
> written. The neighbouring codes it lists were renamed: `invalid_value` and
> `invalid_tracker` no longer exist and `missing_column` is now
> `unrecognised_column`.

> **A likely explanation arrived 2026-08-26, and it is not the one this ticket
> assumes.** [The taxonomy blind-spot audit](70-audit-the-finding-taxonomy-for-blind-spots.md)
> found a second code with the same shape of discrepancy and traced it to the
> emitter's **unit**, not to a coverage gap: `value_not_in_allowed_list`
> reports 1,170 `province` findings across 124 trackers where 26,124 rows in
> those same trackers carry the `Undefined` province sentinel, because
> `validate_allowed_values` iterates `col_values.unique()`. If
> `blank_header_with_data` counts *columns* while ticket 30 counted *values*,
> 217-vs-4,572 is one column carrying many values rather than a missed
> population -- roughly 21 values per column, which is the right order for a
> sheet.
>
> That is a hypothesis, not a finding: the audit did not open the emitter to
> check, and it does **not** explain the other half of this ticket, that the
> code never fires on ticket 30's headline example (`2021_Kantha Bopha` column
> Q) or on any tracker outside 2022. Check the unit first -- it is one read of
> `extract_patient_data` -- because if it holds, this ticket's question changes
> from "why is the emitter missing 95% of them" to "why does it skip whole
> trackers", and the second question is the real one.

> **The unit hypothesis is confirmed, and one of this ticket's two headline
> claims is now false (2026-08-27, from [ticket
> 67](67-findings-must-name-sheet-year-month.md)).** `blank_header_with_data`
> is scoped `sheet_column` -- **one finding per dropped column per sheet**, and
> its message carries the column's value count. Summing those counts over the
> real 255-tracker run gives **4,390 values across 217 findings, 168 sheets and
> 24 trackers**, against ticket 30's catalogue of **4,572**. So the emitter is
> not missing 95% of the population; it is within **4%** of it, and the
> 217-vs-4,572 framing was comparing columns to values.
>
> **"every one of them a 2022 tracker" no longer holds.** `tracker_year` is
> populated for the first time by ticket 67, and the code fires across
> **2017-2023**: 2017 Mahosot (9 findings, 97 values), 2018 Mahosot (12, 230),
> 2021 Putrajaya_DC (10, 19), 2022 (181 across 19 trackers, 3,878 values),
> 2023 Mahosot (2, 163) and 2023 Likas (3, 3). Whether that claim was wrong
> when written or became false as rounds 4-10's extraction fixes landed is not
> established -- the earlier figure was read off file names, and this one is
> the field.
>
> **What is left of this ticket is question 1 and half of question 2.** The
> code still does not fire on `2021_Kantha Bopha` at all -- the only Kantha
> Bopha tracker it fires on is 2022, 12 findings -- so the headline example
> from ticket 30's catalogue is still unexplained, and 2022 still carries
> **84%** of the findings, which wants a reason even though it is no longer
> the whole population. Question 4's premise ("under-states by an order of
> magnitude") is dead.

## Premise

Rests on [Triage the patient pipeline's raw-stage column-existence
divergence](30-triage-patient-raw-column-divergence.md), closed, which
established the population: **26 trackers with headerless columns holding
data, 4,572 values**, the clearest being `2021_Kantha Bopha`, sheets
`Mar21`/`Apr21`, column Q -- **194 insulin-regimen values lost because the
header cell is empty**. That ticket also set the principle the whole reporting
effort serves: where a divergence comes from a human error in the source
workbook, the fix is the workbook, not inference in the pipeline.

Rests on [the findings report](16-log-analyzer-drill-down.md), closed
2026-08-25, which measured the runtime emitter against that catalogue for the
first time.

### The mismatch, measured on the real 255-tracker run (2026-08-25)

`blank_header_with_data` fires **217 times across 24 trackers, every one of
them a 2022 tracker**. Ticket 30's catalogue says 4,572 values across 26
trackers spanning several years.

**It does not fire at all on the catalogue's headline example.** `2021_Kantha
Bopha` produces ten error codes on this run -- `glucose_unit_suspect` (362),
`type_conversion` (135), `invalid_value` (94), `invalid_tracker` (84),
`source_formula_error` (27), `missing_column` (22) and four smaller -- and
`blank_header_with_data` is not among them.

The two numbers come from different machinery and have never been held against
each other: ticket 30's figure came from `src/a4d/migration/compare.py`'s
analysis of raw-stage column divergence against R's frozen output, while the
217 come from the runtime emitter in the extract stage. **Neither is yet known
to be right.**

## Question

Establish which population is real, and make the pipeline report it.

1. **Reproduce the headline case directly against the workbook.** Open
   `2021_Kantha Bopha`, sheets `Mar21`/`Apr21`, column Q on the data drive and
   confirm what is actually there -- 194 values under an empty header, or
   something the 2026 code now handles differently than it did when ticket 30
   ran. The workbook is the evidence; both numbers are derived.
2. **Why only 2022.** A defect class that fires on 24 trackers and all of them
   share one year is far more likely to be a detector keyed to something
   year-specific -- a template layout, a header row count -- than a defect that
   only 2022 clinics committed. Find the gate.
3. **Whether the catalogue's 4,572 is still current.** It was measured before
   several extraction fixes landed (rounds 4-10, ticket 62's `xml:space`
   header work, `find_data_start_row`). Some of those values may now be read
   correctly, in which case the emitter is right and the catalogue is stale --
   which is a legitimate and valuable outcome, not a failure.
4. **What the report should say.** If the true population is thousands of
   values across many years, the report currently under-states a real
   data-loss class by an order of magnitude, and A4D staff are not being told
   about workbooks that need correcting. Say plainly which it is.

## Standing bar

Per the map's **triage means deciding, not labelling** preference, and its
2026-08-13 refinement: the bar is a clear *understanding* of the mechanism,
traced to the source workbook or to the pipeline's own code -- not a verdict
reached by matching two numbers. "The catalogue was measured against a code
state that no longer exists" is a legitimate conclusion; "the detector is
narrower than the defect" is another; guessing which without opening the
workbook is not.


## Resolution (2026-08-27)

**Decision.** Neither population was real. The emitter was reporting **217
findings / 4,390 values** where only **21 findings / 327 values** are a defect
anyone can act on, and the code now reports exactly those. Two classes of false
positive were removed:

- **A column a merged header already names** -- 193 findings, 3,885 values, 21
  trackers. The 2022 template stretches `Insulin Regimen` (merge `K71:L72` on
  2022 Kantha Bopha) and the complication-screening headers across two columns
  each; the right-hand column reads as headerless while the leftmost carries the
  value into the output. Nothing is lost, and the message was telling nineteen
  clinics to fix a header that is not broken.
- **The row counter carrying one stray keystroke** -- 3 findings, 178 values.
  The all-numeric guard failed on a single cell: `'m'` among 83 row numbers in
  2023 Mahosot's Sep23, a lone `' '` in 2022 Children's Hospital 2's Oct22.

**What is left is real.** 2017/2018 Mahosot, column S, 327 values all reading
`Mixtard30 Penfill (3ml x 5's/box)`, sitting unlabelled between
`Estimated Insulin Required per year` and `Estimated Testing Strips per month`.
No sibling sheet names it, so `recover_blank_headers` cannot help. That is a
genuine workbook defect and stays reported.

**Question 1 answered by execution, and the ticket's premise was the fix
working.** Running `find_dropped_data_columns` / `recover_blank_headers` on
`2021_Kantha Bopha` directly: `Mar21` and `Apr21` each drop column Q holding
**97** values, the siblings donate `"Insulin Regime"` unanimously, recovery
fires, and the emitter then returns nothing. 97 + 97 = **194** -- ticket 30's
exact headline number. The code does not fire on the catalogue's clearest
example because ticket 30's own recovery already fixed it.

**Question 2 answered.** 2022 carried 84% because it is one template's
formatting habit replicated across 19 trackers, not a defect 2022 clinics
committed. The gate was that `find_dropped_data_columns` never received the
merge spans, while `recover_blank_headers` -- one function away, in the same
file -- computed them and skipped exactly these columns. The map's
"never hand-maintain what can be derived" rule biting again: the same exclusion
existed twice and only one copy was applied.

**Question 3.** Ticket 30's catalogue of 4,572 is not stale, but it counted the
same false population. Its own resolution said "most of the 4,572 are the 2022
template's hidden merged-cell column that Python is right to drop" -- that was
correct, and the mechanism is now named: it is not hidden, it is the second
column of a merged header.

**Question 4 inverts.** The report **over-stated** this class by roughly 13x. It
was not failing to tell A4D staff about workbooks needing correction; it was
burying the two workbooks that do need it under 196 that do not.

**Because.** A merged header is the workbook's own statement that the columns
beneath it are one block -- the evidence `merged_header_spans` was added to read
in the first place. Content buried under the right-hand half of a merge is not
displayed by Excel, so a clinic cannot see it, cannot act on it, and on 2022
Kantha Bopha's Apr'22 sheet 115 of its 161 values are byte-identical to the
anchor column anyway.

**Rejected.**

- *Report the buried content under a new code* (the 46-of-161 rows on Apr'22
  where the shadow differs from the anchor are stale pre-merge content). Killed
  by the user: a permanent glossary entry for something invisible in Excel and
  not correctable at the clinic. **What this gives up:** if a workbook ever
  carries meaning in the right-hand half of a merged header, the pipeline drops
  it silently. Judged acceptable because Excel drops it visually first.
- *Leave it and explain the noise in the glossary.* Rejected: the message
  instructs an edit that is not needed, on 90% of its rows.
- *Identify the row counter by its numbers counting upward, full stop.* Tried
  and **measured false** -- it took the code to 95 findings, not 21, because
  counters that restart or hold a single number stopped qualifying. The
  ascending test is now asked only of the one-stray case, so the pre-existing
  all-numeric behaviour is untouched.

**Evidence: executed.** Every number here is from running code against the real
255-tracker corpus on the data drive, not from reading.

- A sweep re-derived all 217 pre-fix findings from the workbooks and reproduced
  the run exactly (217 findings, 4,390 values), then classified each by merge
  coverage -- 193 / 3 / 21.
- The Kantha Bopha 2021 recovery was run function-by-function on the workbook.
- The 2022 Kantha Bopha merge (`K71:L72`, 166 K:L row merges) was read from the
  file, and column L's values compared against column K row by row.
- Full local both-arm run before and after: findings **103,603 -> 103,407**,
  which is exactly -217 + 21 and nothing else. `blank_header_with_data`
  **217 -> 21**, codes firing **40 -> 40**. `patient_data_static` (1,828),
  `patient_data_monthly` (86,360), `patient_data_annual` (4,520) and
  `product_data` (75,169) unchanged, so no published data moved.
- Suite green: 1,328 passed, 1 skipped. Six new unit tests cover the merge
  exclusion, the one-stray counter, whitespace-only cells, and the two
  regressions the first attempt caused.

**A real population was found inside the suppressed set, and spawned [ticket
75](75-screening-selections-under-merged-header.md).** Splitting the 193 merge
shadows by what the merge names gives two unrelated things: `Insulin Regimen`
(103 findings, 3,659 values, **2,910 byte-identical to the anchor column**) is
residue, but the complication-screening block (90 findings, **226 values, 12
trackers**) duplicates the anchor **zero** times -- those are additional
screening results the pipeline discards after the first. They had visibility
only by accident, under a message that described them wrongly, and this session
removed it. That is a knowing step backwards, recorded as ticket 75 and as an
entry in the map's **Assumptions in force**.

**Tense.** Everything above describes current behaviour on `dev` after this
session's commit, except the Rejected entries, which describe designs not taken.
