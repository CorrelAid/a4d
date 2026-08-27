---
id: 77
title: The 2023 template records which month each screening was done, and the pipeline has nowhere to put it
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-27b
claimed_at: 2026-08-28T02:00:00+02:00
resolution: out-of-scope
evidence: executed
closed_by: 75
spawned_by: 75
---

## Premise

Rests on [A screening block records several results per patient and the pipeline
keeps only the first](75-screening-selections-under-merged-header.md), closed
2026-08-28, which published the complication-screening selection for the first
time. Doing so made visible that the column carried two different fields
depending on the template year, and ticket 75 separated them: the selection
column now holds only the 2021/2022 "which screenings were done this month"
drop-down.

The 2023 template asks a different question, one column per test -- kidney, eye,
foot, lipids, blood pressure, TSH, tTG-IgA -- and the clinic types the **month
that test was completed** into it. Seven source columns; five of them were
mapped onto the selection column and comma-joined there, which is how a
patient-month came to read `MAR,MAR`. Ticket 75 unmapped those five, so all
seven are now reported as columns the pipeline does not recognise rather than
joined into a value that is false.

**What would void this ticket rather than rewrite it**: if A4D confirms the
2023 per-test completion months were a template experiment that did not survive
into 2024+ and are not wanted. The map's standing rule that the current template
is the golden rule points that way and should be checked first -- see the
question below.

## Question

**3,638 cells across 25 trackers, all 2023**, record the month a specific
complication screening was completed. None of them reaches any published table
today, and none did before ticket 75 either -- they were joined into a column
that was itself discarded.

1. **Does the current template still ask this?** The map's standing rule is that
   the current tracker template is the golden rule, and a field that appears in
   one year and is gone the next was very likely a test that did not survive.
   Measure 2024/2025/2026 first: if the per-test completion columns are gone,
   the answer is probably to report them and stop, and this ticket is small.
2. **If they are wanted, where do they go?** The output already carries a date
   per test -- kidney, eye, foot, lipid profile, thyroid. A bare month name with
   no year would have to take the tracker's own year, which is an inference, and
   the month recorded need not be the sheet's month. There is no column at all
   for blood pressure or tTG-IgA completion.
3. **Either way, is the current report good enough?** The seven columns now
   surface as unrecognised columns, which tells A4D the pipeline has no home for
   them but not that clinical dates are going unpublished.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: confirming
the columns are reported is not the decision. Whether 3,638 recorded screening
dates should be published has to be answered, and measured against the current
template before it is.

## Resolution

**Decision.** Out of scope. The 2023 per-test completion-month columns are
reported and not published, which is what the map's standing rule already
prescribes for them. No further work.

**Because.** The ticket asked its own question 1 first, as it said to: whether
the current template still asks for these columns. It does not. Across the
254-tracker corpus the seven "Complication Screening Completed <test>" headers
appear in **2023 only** -- 2,471 findings across 33 trackers, and **zero**
instances in 2024, 2025 or 2026.

That puts them squarely inside the user's standing decision of 2026-08-15, which
the map records under **Out of scope**: the current tracker template is the
golden rule, a column that appears in one year and is gone the next was very
likely a test that did not survive, and such columns are *detected and reported*
rather than inferred into the pipeline. That decision already names `TSH` and
`tTG-IgA` -- two of these very seven -- among the 68 columns it covers.

Ticket 75 already put them in the reported state the rule asks for: they surface
as unrecognised columns rather than being fused into a value that was false.
There is nothing left to decide.

**Rejected.**
- *Publish them into the existing per-test date columns.* This ticket's own
  question 2, and the reason it was written. Moot once the columns are shown to
  be a dead template branch, and it would have meant inferring a year onto a
  bare month name to serve one year of one retired layout.
- *Leave the ticket open pending a word from A4D.* The standing rule is the
  user's decision and it is not conditional; keeping the ticket alive would put
  a settled question back on the frontier.

**Evidence: executed.** The year breakdown is a query over the findings table of
the full 254-tracker both-arm run: `unrecognised_column` findings whose column
name begins "Complication Screening Completed", grouped by tracker year -- one
row, 2023.

**Tense.** The year distribution is current measured behaviour. The claim that
these columns were a template experiment is the user's standing reading, not
something this session established.
