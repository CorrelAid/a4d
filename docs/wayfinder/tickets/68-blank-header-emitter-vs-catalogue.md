---
id: 68
title: The pipeline reports 217 headerless-column defects where the triage found 4,572
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
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
