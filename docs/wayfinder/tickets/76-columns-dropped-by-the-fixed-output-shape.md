---
id: 76
title: Everything the pipeline reads out of a workbook and then discards to fit the fixed output shape
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 75
---

## Premise

Rests on [A screening block records several results per patient and the pipeline
keeps only the first](75-screening-selections-under-merged-header.md), closed
2026-08-28, which found that the complication-screening selection and its result
were read out of every workbook and then dropped, because the cleaned output has
a fixed column list and neither was on it. Nothing reported the drop. Ticket 75
fixed those two columns by adding them to the list; it did not touch the
mechanism.

Rests on [What can go wrong in a tracker that the pipeline never reports at
all?](70-audit-the-finding-taxonomy-for-blind-spots.md), closed, which audited
the finding taxonomy for blind spots and did not reach this one -- the audit
looked at what the emitters cover, and this is a whole stage with no emitter at
all.

**What would void this ticket rather than rewrite it**: if the fixed output
shape is found to be enforced somewhere that already reports the columns it
drops. Ticket 75 read the function that applies it (`clean/schema.py`,
`apply_schema`) and it selects the schema's keys with no reporting of any kind.

## Question

Applying the fixed output shape is a `select` of the 85 named columns. Anything
else the extraction produced is discarded there, silently -- no finding, no log
line, nothing in the report a clinic or A4D staff member reads.

Measured on the 254-tracker corpus: **73 distinct column names carrying 63,790
values** are dropped this way. They are not one population:

- **Consumed, correctly dropped.** `blood_pressure_mmhg` (19,273 values, 73
  trackers) is split into systolic and diastolic before the shape is applied,
  so the source column has done its job. Several others are like this.
- **Deliberately excluded.** Phone numbers, contact numbers and insurance-card
  fields (roughly 5,000 values) look like data the output is meant not to carry.
  Nobody has confirmed that, and it is not written down anywhere.
- **Genuinely lost, nobody told.** `complication_screening` and
  `complication_screening_results` were in this group until ticket 75. What else
  is in it is not known -- candidates from the measurement include
  `est_strips_pmoth` (3,749 values, 22 trackers), `insulin_dosage` (2,533, 8),
  `meter_received_date` (1,788, 17) and `complication_screening_date` (397, 19).

The measurement above was taken from a previous run's raw parquets; re-derive it
against a current run before deciding anything on it.

The question has two halves:

1. **Which of the 73 are in the third group**, and should any of them reach the
   published tables the way ticket 75's two now do?
2. **Should the drop be reported at all**, and if so how -- one finding per
   dropped column per workbook would be noisy for the columns that are
   deliberately excluded, so a declared list of "read and discarded on purpose"
   is probably the shape, with anything outside it reported.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: sorting the
73 into three buckets is not the decision. Each column in the third group needs
a decision about whether it is published or reported, and ticket 27's precedent
applies -- a classifier that explains a drop without deciding it cements the
loss as "understood".
