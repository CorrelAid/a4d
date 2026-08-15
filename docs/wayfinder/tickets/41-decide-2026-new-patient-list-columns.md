---
id: 41
title: Decide whether the 2026 template's five new Patient List fields enter the pipeline
labels: [wayfinder:grilling]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 30
---

## Premise

Rests on [Triage the patient pipeline's raw-stage column-existence
divergence](30-triage-patient-raw-column-divergence.md), closed, which found
these columns while accounting for the only-in-Python divergences, and on the
user's rule stated in that session: **the current tracker template is the
golden rule** -- a column present in today's template is the kind that matters,
where one that appeared for a single year and vanished is very likely a test
that did not survive. These five are the former case, which is why they are
ticketed rather than ruled out.

Verified against the source workbook
(`2026_Preah Kossamak Hospital A4D Tracker_Jun_26.xlsx`, `Patient List` sheet,
header row 8): the 2026 template carries five columns with no entry in
`reference_data/synonyms/synonyms_patient.yaml` and no home in the 83-column
cleaned schema:

| Col | Header | Populated |
|---|---|---|
| 17 | `Phone Number` | |
| 18 | `Insurance Card Status` | |
| 19 | `Current Insulin Regimen` | 213 rows |
| 20 | `BGM A4D` | 213 rows |
| 21 | `Insulin A4D` | 213 rows |

Python's raw stage passes them through under their literal header text (its
`ColumnMapper` runs non-strict); the cleaning stage drops them, since the
schema has no such columns. R does the same thing under sanitized names
(`currentinsulinregimen`, `bgma4d`, ...), so neither pipeline carries them
forward -- this is a **new-field question, not a Python defect**.

**`Current Insulin Regimen` is not the monthly `Insulin Regimen`.** Measured on
the same file: both columns exist, 191 rows have both populated, and they
**disagree on 39** of those. Mapping the Patient-List column onto
`insulin_regimen` would corrupt data. It is a patient-level field beside the
month-by-month one.

## Question

The user said they need to look at the new 2026 trackers themselves before
deciding -- so this ticket waits on that inspection, and the decision is
theirs.

For each of the five: does it enter the pipeline as a new cleaned-schema
column, or stay a raw-stage passthrough that is deliberately dropped?

Things the decision turns on, worth having ready when it is taken:

1. **How widely each column is actually used** -- only one clinic's 2026
   tracker is in the current set. Check the 2026/2025 master template rather
   than this single file before concluding it is standard.
2. **Blast radius of saying yes.** A new cleaned-schema column means
   `clean/schema.py`, the synonym file, the patient tables, and the BigQuery
   schema -- and a BigQuery schema change touches the production load path
   ([ticket 5](05-production-verification-run.md)'s territory).
3. **Whether `Current Insulin Regimen` needs a distinct name** to keep it from
   ever colliding with the monthly `insulin_regimen` -- the 39 disagreeing rows
   are the evidence that it would.
4. **Whether this belongs to this map at all**, or to the post-promotion
   backlog. The destination is "close out the R-to-Python migration"; adding
   fields R never had is arguably new development, not migration. Deciding that
   is part of this ticket.
