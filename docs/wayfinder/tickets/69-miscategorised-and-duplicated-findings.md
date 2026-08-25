---
id: 69
title: The biggest finding code is a recovery filed as data loss, and every age finding is emitted twice
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

Rests on [Unify the two separate channels that report data-quality
findings](66-unify-finding-channels.md), closed 2026-08-25, which made
`category` derived from the error code rather than passed per call site, and
collapsed **six** pairs of findings that were each being emitted twice -- once
per channel. Its own tests keep `FINDING_CATEGORY` exhaustive over `ErrorCode`,
so a code cannot ship uncategorised; nothing checks that the category it gets
is the *right* one.

Rests on [the findings report](16-log-analyzer-drill-down.md), closed
2026-08-25, whose Summary sheet ranks trackers by their `fix_workbook` and
`data_lost` counts. Both defects below therefore change what an operator sees
first, not just what a table holds.

Found while auditing the report's glossary against the emit sites, after the
user challenged the `invalid_tracker` description as impossible: 22,394
findings across 255 trackers cannot mean "the workbook could not be read as a
tracker at all". That entry was wrong, and checking the rest turned up these
two, which are defects in the taxonomy rather than in its prose.

### Defect 1: `missing_value` is a recovery filed as data loss

`missing_value` is the **largest single code on the run -- 27,038 findings**,
categorised `data_lost`, which the glossary renders as "the cell could not be
used and its value is gone from the output".

It has exactly two emit sites, both in `_fix_age_from_dob`
(`clean/patient.py:767` and `:776`), and both fire when the patient's **age
cell was empty and the age was calculated from their date of birth and
published**. Nothing is lost. It belongs in `recovered`.

The distortion is material: `data_lost` totals **71,566**, so **38% of the
"data lost" column is data that was recovered**. That is the column the report
ranks trackers by.

### Defect 2: every `_fix_age_from_dob` finding is emitted twice

The same function reports each event twice -- once without `patient_id` or
`column`, once with -- because the two calls were written for two different
readers. Measured, and the split is exact:

| code | total | without `column` | with `column` |
|---|---|---|---|
| `missing_value` | 27,038 | 13,519 | 13,519 |
| `invalid_value` | 5,122 | 2,561 | 2,561 |

**16,080 duplicate rows, 13% of the entire findings table.** This is the
seventh and eighth instance of the exact pattern ticket 66 collapsed six of;
it was missed because both copies go through `report_finding` and so look
like two legitimate findings rather than one finding on two channels.

### What else the audit found, already fixed

Eleven of the twenty-one glossary entries were rewritten in the same session
after being checked against their emit sites, and the misleading `#` comments
beside `ErrorCode` were corrected with them. Two names remain wrong and are
part of this ticket's question:

- **`missing_column` does not mean a column is missing.** It fires from
  `reference/synonyms.py:221` -- "Keeping N unmapped columns as-is" -- when a
  column in the *tracker* matches nothing in the reference list. It is an
  unrecognised column, the opposite of an absent one. 3,116 findings across
  254 of 255 trackers.
- **`invalid_tracker` is not a tracker-level failure.** Fifteen emit sites,
  every one a per-sheet or per-section problem where that part is skipped and
  the rest of the workbook still processes. 22,394 findings across all 255
  trackers.

## Question

1. **Recategorise `missing_value`** to `recovered`, or split it: the code name
   describes the *input* (a cell was empty) while the category must describe
   the *outcome* (a value was published anyway). Decide which the taxonomy is
   keyed on, because the same tension will recur.
2. **Collapse the duplicate emission** in `_fix_age_from_dob`, keeping the copy
   that names the patient and column. Check whether the stage-level copy's
   message carries anything the cell-level one does not before deleting it.
3. **Rename `missing_column` and `invalid_tracker`**, or decide the names stay
   and the glossary carries the correction. These are values published into
   BigQuery, so renaming changes output that consumers may filter on -- the
   same consideration that made [ticket 65](65-logs-table-r-named-values.md)
   a ticket rather than an edit.
4. **Guard the category, not just its exhaustiveness.** Ticket 66's tests
   prove every code *has* a category; nothing proves it is right, which is why
   the largest code on the run has been mis-filed since it landed. Decide what
   a meaningful check looks like -- most likely asserting the category against
   what each emit site actually does with the value, per code.
5. **Re-measure after the fix.** The 122,590 total, the 71,566 `data_lost` and
   the report's tracker ranking all move. Any number quoted elsewhere on this
   map from the 2026-08-25 run is superseded.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: read the
emit sites, do not infer the meaning from the code name -- that is exactly the
mistake that produced both the wrong glossary and the wrong category.
