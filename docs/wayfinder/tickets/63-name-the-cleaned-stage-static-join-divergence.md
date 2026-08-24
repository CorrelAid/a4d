---
id: 63
title: The cleaned stage has 3,593 cells with no cause, because the ID spelling that explains them is gone by then
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 58
---

## Premise

Rests entirely on [Monthly rows with a misspelled ID silently lose their
Patient List demographics](58-patient-list-join-uses-unfixed-id.md), closed,
which made both whole-tracker joins key on a normalized `patient_id` and so
recovered 680 rows / 6,863 Patient List cells that R still publishes as null.

That decision also established the constraint this ticket exists inside: the
new cause `r_static_join_misses_respelled_id` can only fire on the **raw**
stage, because its discriminator is the month row's own ID still carrying the
hyphen or transfer-clinic suffix -- and cleaning normalizes exactly that, on
both sides. Raw-stage `unclassified` is now **0**; cleaned-stage went **16 ->
3,593**.

Also rests on the map's standing bar (**triage means deciding, not
labelling**): a cause carrying the right label over the wrong reason is what
[ticket 62](62-finish-the-pre-bar-classifier-audit.md) found three times over,
so widening `r_extraction_gap` to swallow these is explicitly not the answer.

**What would void this ticket rather than rewrite it:** ticket 58's join fix
being reverted, since without it these 3,593 cells do not exist.

## Question

1. **Find a discriminator that survives cleaning.** Candidates: have the
   comparison carry the raw spelling forward as a diagnostic flag on
   `CellMismatch` (the shape `row_order_candidate` and
   `group_endpoint_matches` already use); or derive the affected identities
   once per file and match on those; or have cleaning record the
   pre-normalization ID in a column. Each has a different reach -- the first
   two touch only the comparison, the third changes production output.
2. **Bound the three columns the corpus-wide wiring over-claimed on.** Ticket
   58 measured that `t1d_diagnosis_age` (1,069 rows against a join-miss
   population of 679), `bmi` (144) and `age` (1) also carry R-null/Python-present
   cells for these patients from some *other* mechanism, because the month
   sheets carry those columns too. They currently keep their pre-existing
   causes. Measure what those other rows actually are and whether their
   current cause states the right reason -- this is a ticket-32-shaped
   question, not a wiring question.
3. **Check what absorbed the new cells before the bounded wiring landed.**
   `recruitment_date` went 28,085 -> 28,762 in the first post-fix comparison
   with no `unclassified` movement, which means an existing cause
   (`r_extraction_gap`, whose documented mechanism is R's `xml:space` header
   defect) silently took 677 cells that belong to the join miss. Confirm no
   other column is still in that state on the cleaned side.

## Standing bar

Per the map's **triage means deciding, not labelling**: measure before
proposing, and a classifier is only written once the mechanism is traced.
