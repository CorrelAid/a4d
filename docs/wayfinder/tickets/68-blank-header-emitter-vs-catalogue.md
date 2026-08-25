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
