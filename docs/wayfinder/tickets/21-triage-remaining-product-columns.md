---
id: 21
title: Triage the remaining product cleaned-stage column mismatches (balance, received_from, released_to, remarks, units_received, product)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 18
---

## Premise

Rests on [Triage every flagged R/Python difference for both arms, and
resolve the 189-vs-155-tracker discrepancy](18-triage-comparison-flagged-differences.md),
closed: the product row-alignment key is sound (ticket 17, 97.2% match) and
`product_category`/`product_entry_date` are already root-caused and
classified. This ticket inherits the remaining `product_data_cleaned`
per-column mismatch counts from that session's `just compare-outputs` run,
unexamined: `product_balance` (2,343), `product_received_from` (330),
`product_released_to` (3,834 — not among the causes the parity-presentation
PDF named at all, so there is no prior baseline count to compare against),
`product_remarks` (66), `product_units_received` (265), and `product` itself
(652 — the product name/identity column disagreeing is a different kind of
divergence than a value column and may need its own explanation).

Also rests on the 189-vs-155-tracker finding: per-column counts are not
expected to reproduce the PDF's numbers exactly, since the PDF's baseline
population is provably different and unreachable — the bar is explaining
each divergence's pattern, not hitting an exact count (per ticket 18's
resolution).

**Updated same day, per ticket 18's addendum:** R and Python were both
re-run against the current 248-tracker production set (up from 177) and
`output_r/` now holds that fresh R output (old baseline preserved at
`output_r_155_frozen_backup_2025-11-14`). This changed the picture
significantly for the columns already root-caused (`product_category`
dropped from 13,638 to 866 mismatches — most of the old count was baseline
staleness, not the join-logic bug itself) and moves the 189-vs-155
question closer to reconciled (229/66,020 now, vs the PDF's 189/61,077).
Refreshed counts for this ticket's remaining columns (same run,
`output/comparison/2026-08-11T232419Z/`): `product_balance` 2,740 (was
2,343), `product_received_from` 366 (was 330), `product_released_to` 4,490
(was 3,834), `product_remarks` 70 (was 66), `product_units_received` 305
(was 265), `product` 652 (unchanged), plus a new `file_name` mismatch count
of 60 not seen in the original session (unexplained — check whether this is
a new comparison-tool column or a real divergence before assuming it's in
scope here). Use the current `output_r`/`output_python`, not the backup.

## Question

For each of `product_balance`, `product_received_from`, `product_released_to`,
`product_remarks`, `product_units_received`, and `product`: pull the flagged
mismatch rows (`just compare-outputs`'s `cell_mismatches` sheet, cleaned
stage), look for a systematic pattern the way ticket 18 found for category/
entry_date (e.g. is it also majority R-null-Python-has-value, or a different
shape entirely), fall back to the real source Excel trackers
(`a4dphase2_upload`) as the arbiter, and add a named cause to
`src/a4d/migration/compare.py`'s classifier registry once a pattern is
confirmed. `product_released_to` in particular has no PDF precedent to
compare against — start by establishing whether it's a real divergence or
another comparison-tool artifact (per ticket 20's finding that at least one
column had a false-positive representation issue) before assuming it needs
a data explanation.
