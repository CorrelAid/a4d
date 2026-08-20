---
id: 59
title: Rows that pair with nothing on the other side, which no ticket has ever triaged
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 47
---

## Premise

Rests on [Four trackers where cleaning merges several patients into one patient
ID](47-patient-ids-merged-at-cleaning.md), closed, whose comparison re-run
exposed this. That ticket's four recovered rows stop pairing with R, and
finding *which* rows they were required querying the parquets by hand -- so
`RowKeyOverlap` was extended to carry the unmatched keys, not just their
counts, and the report gained a `row_key_unmatched` sheet.

The sheet's first run named a population nobody had looked at. Measured
(executed) against the real 254-tracker output on the USB drive:

- **Patient cleaned: 144 unmatched rows across 7 files.** Only 8 of them are
  ticket 47's (`2023_NPH`, 4 R-only + 4 Python-only). The rest:
  `2026_Preah Kossamak…_Jun_26` 98 R-only, `2022_Children's Hospital 2` 15
  R-only, `2024_Mandalay Children's` 11 Python-only,
  `2026_Quirino Memorial…_Jun_26` 5 R-only, `2026_YGH…_June_26` 3 R-only and 3
  Python-only, `2024_Mahosot Hospital` 1 Python-only.
- **Patient raw: 130 unmatched rows.**
- **Product, both stages: 0** -- resolved by
  [ticket 17](17-fix-product-row-alignment-and-triage.md)'s ordinal key.

This population is structurally invisible to every triage ticket the map has
run. A row with no partner never reaches `compare_cells`, so it appears in no
`cell_mismatches` sheet, contributes to no per-column or per-cause count, and
cannot be classified -- the ten-round patient chain worked exclusively off
those counts. It is the same shape of gap as `compare_columns` was before
[ticket 26](26-triage-product-column-divergence.md).

**What would void this ticket rather than rewrite it:** the counts turning out
to be an artifact of the row-alignment key rather than of the data, which
[ticket 45](45-patient-row-alignment-duplicate-keys.md) settled for patient
(the key is unique in 249 of 254 files) -- so this is unlikely, but it is the
thing to check first.

## Question

1. **Is this a divergence at all, or a shape difference?** A whole tracker
   present on one side only is already reported separately as a file-level
   finding; these are *rows* inside files both sides produced. Establish
   per file whether R is holding rows Python drops, Python is producing rows R
   never had, or the two are the same rows keyed differently.
2. **Start with `2026_Preah Kossamak…_Jun_26`'s 98 R-only rows**, the largest
   single population and 68% of the patient cleaned total. 98 rows is a
   plausible whole clinic-month.
3. **Decide each, to the map's standing bar** -- for every group, whether
   Python is right, R is right, or the source workbook is defective. Ticket
   47's four rows are already decided (Python correct, recorded there) and
   should be excluded rather than re-argued.

## Standing bar

Per the map's **triage means deciding, not labelling**. Note that the usual
instrument does not work here: there is no cell mismatch to classify, so the
cause registry cannot carry the answer and the resolution comment has to.
