---
id: 39
title: Decide whether a date buried inside a clinical note should be recovered or discarded
labels: [wayfinder:grilling]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 38
---

## Premise

Rests on [Triage the patient cleaned-stage date-column family (round
3)](38-triage-patient-cleaned-date-family.md), closed, which established three
things this ticket depends on:

- **A date cell that records an absence is now nulled, not sentinelled.**
  `MISSING_VALUE_MARKERS` / `DATE_ABSENCE_MARKERS` /
  `DATE_PLACEHOLDER_FRAGMENTS` (`src/a4d/clean/date_parser.py`). That removed
  4,377 of the 6,186 sentinel-stamped date cells, so what remains is no longer
  contaminated by blanks -- this ticket's 1,809 rows really are cells where
  *something* was written.
- **R is not a usable oracle here.** R's `parse_dates` recovers a date from
  some of these strings and is demonstrably wrong on others: `"admitted to
  Pokaku Hosp due to DKA 7-15 Apr"` -> R gives `2015-07-01`; `"DKA: admitted
  6-12 Nov 2020"` -> R gives `2020-12-06` (the range's two numbers read as
  day and month); `"9-Dce-20"` -> R gives `2020-09-01`, discarding the
  transposed "Dce". So "match R" is not available as an answer, and any
  divergence this ticket creates from R needs its own justification.
- **Ticket 37 already added a longest-parseable-prefix fallback**, which
  handles a date at the *start* of the string (`"16-Nov-2019 due to DKA"`).
  This ticket is about the other direction -- the note comes first and the
  date is inside or at the end.

Overturned only if the destination stops requiring that Python's own output be
defensible on its own terms; it survives R's retirement (ticket 12) intact,
because it is a question about Python's behaviour, not about parity.

## Question

**1,809 cleaned date cells across 296 distinct source texts currently become
the error sentinel because a real, legible date is embedded in a clinical
note.** Measured on the real 254-tracker set after ticket 38's fix, largest
first: `t1d_diagnosis_date` 559, `hospitalisation_date` 540, `bmi_date` 126,
`fbg_updated_date` 124, `hba1c_updated_date` 86, then the four
complication-screening date columns and a tail.

Representative texts, all of which a human reads without hesitation:

```
DKA 23 Oct 2020
Passed away 28/10/2019 due to DKA
DKA 30-Nov-2020 (Meikhtila hospital)
7/04/2021: DKA
22nd Feb.2019(DKA)
May'21: Rx at Emergency room Hyperglycemia with Ketosis
```

And the ones that make this a decision rather than a task:

```
DKA: admitted 6-12 Nov 2020          (a range -- which endpoint?)
DKA 2020: June, Aug, Nov             (three events in one cell)
admitted ... due to DKA 7-15 Apr     (a range, and no year at all)
DKA 2019                             (a year, no month -- invent Jan 1?)
10-มค-2025                            (Thai month abbreviation)
```

Decide, with a recommendation rather than a survey:

1. **Do we recover these at all**, or is the sentinel plus the error log the
   right home for "a date is in here somewhere"? Note what is lost either way:
   discarding loses a real hospitalisation date the clinic recorded; recovering
   risks asserting a precise date the source did not state.
2. **If we recover: how strict?** An anchored, unambiguous pattern (day +
   month-name + 4-digit year, and nothing that looks like a range) recovers
   the clean majority and refuses the ambiguous tail. dateutil's `fuzzy=True`
   recovers more and invents more -- it is how R gets `2015-07-01` out of
   `"7-15 Apr"`.
3. **Where does an ambiguous cell go?** Sentinel, null, or first-endpoint-with-
   an-error-log-entry are all defensible; they are not the same claim.
4. **Does `hospitalisation_date` want a different answer from the rest?** It is
   the only column where clinicians routinely write prose -- the template's own
   sub-header says "(Insert Date or NA)" and they write a case note anyway.
   `t1d_diagnosis_date`'s 559 rows may have a different shape entirely and are
   not yet characterized.

Whatever is decided, the corresponding cause needs naming in
`src/a4d/migration/compare.py` so the R-vs-Python report stops carrying these
as `unclassified` -- 487 of them currently sit there.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: it is not
enough to explain a difference and name a cause. Each one must also carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Where
Python turns out to be wrong or to be losing information the source file
carried, fix the pipeline rather than labelling the symptom. A cause genuinely
undecidable on available evidence is recorded as an open question, not closed
with a label; where the evidence shows the source file itself is corrupt,
"the source is wrong, this tracker needs human inspection" is a legitimate
final conclusion.
