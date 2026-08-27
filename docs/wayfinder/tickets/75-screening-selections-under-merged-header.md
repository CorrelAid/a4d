---
id: 75
title: A screening block records several results per patient and the pipeline keeps only the first
labels: [wayfinder:grilling]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 68
---

## Premise

Rests on [The pipeline reports 217 headerless-column defects where the triage
found 4,572](68-blank-header-emitter-vs-catalogue.md), closed 2026-08-27, which
established that a column sitting under a merged header is named by that merge
and is no longer reported as a headerless data column. Splitting the 193
suppressed findings by what the merge names showed they are two unrelated
populations, not one:

- **`Insulin Regimen`** -- 103 findings, 3,659 values, 10 trackers, of which
  **2,910 values are byte-identical to the column the merge anchors**. Stale
  content buried under a merge, invisible in Excel. Correctly dropped.
- **the complication-screening block** -- 90 findings, **226 values across 12
  trackers**, of which **zero** duplicate the anchor column. These are
  additional screening results, one per column, and the pipeline keeps only the
  first.

Rests on [Python drops complication-screening results and dates where a merged
header spans them](48-putrajaya-screening-columns-lost.md), closed, which found
the same shape on `2021_Putrajaya` and deliberately did not fix it: both
pipelines keep only the first selection, so the R/Python comparison stays silent
and it is a shared limitation rather than a divergence.

**This was the map's "multi-select screening block" fog patch**, which said it
was not sharp enough to ticket "until someone has measured how many trackers lay
a block out this way". Ticket 68 measured it: **12 trackers, 226 values**.

**What would void this ticket rather than rewrite it**: if ticket 68's
merge-coverage classification is wrong -- that is, if these columns are not
under a merged header at all -- the population disappears and there is nothing
to decide. Ticket 68's own reversal, were it overturned, would only change how
these are *reported*, not whether they are dropped.

## Question

A clinic records several complication screenings for one patient in one month --
`Foot Examination (Nerves)`, `Lipid profile`, `TSH` -- by putting each in its own
column under a single merged "Complication Screening" header. The pipeline
publishes the first and discards the rest.

Until ticket 68 this was at least *visible*, though under a message
(`blank_header_with_data`, "fix the header in the source tracker") that
described it wrongly -- the header is not missing, and there is nothing for the
clinic to fix. Ticket 68 removed that message, so as of now these 226 values are
dropped in **total silence**. That is the state this ticket has to resolve, and
it is a step backwards taken knowingly.

1. **Are the extra selections wanted downstream?** The published patient tables
   carry one screening column. Answering "yes" means a schema question, not just
   an extraction one: several results per patient-month have to land somewhere.
   Ask the consumer (the internal tool and the dashboard) before designing.
2. **If they are wanted, what shape?** A delimited list in the existing column,
   one row per screening, or additional columns -- and what that does to
   consumers already reading the single-value column.
3. **If they are not wanted, they must still be reported.** Silently discarding
   226 clinical results is what the map's blind-spot audit exists to prevent.
   A code naming what actually happened ("this patient-month recorded 3
   screenings, 2 were dropped") is a different statement from "your header is
   missing", and is the minimum outcome of this ticket.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: naming the
class is not the decision. Ticket 27's precedent applies directly -- what looked
like a labelling job was extraction silently discarding data, and a classifier
would have cemented the bug as "explained".

Measure before designing: the 226 values are known, but how many are *distinct*
per patient-month, how many patient-months carry more than one, and which
trackers and years, are not.
