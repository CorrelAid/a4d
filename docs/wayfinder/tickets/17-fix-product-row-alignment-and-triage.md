---
id: 17
title: Fix the product comparison's row-alignment key, then triage every flagged R/Python difference
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 15
---

## Premise

Rests on [Build and run the R/Python output comparison script, then triage
every flagged difference](15-build-and-run-comparison-script.md), closed:
`scripts/compare_outputs.py` + `src/a4d/migration/compare.py` are built,
tested (23 unit tests), and were run against a fresh Python pipeline pass
(both arms) and the frozen `output_r/` baseline, both on the USB drive.

That session found the patient arm's row-alignment key —
`(patient_id, sheet_name)` — is sound (duplicate keys in only 5 of 172
matched files, each a handful of rows) and can be triaged as-is. It found
the **product arm's key is broken**: `(clinic_id, product,
product_sheet_name, product_entry_date)` collapses onto far fewer distinct
keys than rows exist (one file alone: 154 distinct keys for 1,194 rows, up
to 35 rows sharing a key) because `product_entry_date` is null on many rows
(balance-only or malformed-date rows). Every duplicate group produces a join
fan-out that inflates reported cell-mismatch counts by orders of magnitude
and — critically — excludes `product_entry_date` itself from
classification, since it's one of the join keys. The PDF's single largest
divergence column (`Product_entry_date`, 559 mismatches) currently never
gets diffed at all. This was confirmed by direct `group_by` inspection
against the real drive data, not inferred.

That session also left unreconciled: the parity-presentation PDF cites 189
trackers / 61,077 rows for product; this session's fresh run matched 155 R
product files (0 only-in-R, 19 only-in-Python — explained by [ticket
14](14-product-column-detection-failures.md)'s 0-row-output fix for
pre-product-tracking years). Whether that gap is a stale PDF number, a
different drive snapshot, or something else is not yet investigated.

## Question

Design and implement a row-alignment key (or an alignment strategy that
isn't a simple equi-join key — e.g. an ordinal position within a group,
possibly reusing the `index` column `clean/product.py` already assigns per
`(clinic_id, product_sheet_name)` at step 2.5 but doesn't currently carry
into the output schema) that uniquely identifies a product row well enough
for `compare_cells` to align R and Python rows without fan-out — including
rows where `product_entry_date` is null. Confirm R and Python assign the
same ordering for whatever key is chosen (they may not, if extraction order
differs) before trusting any diff built on it.

Once alignment is fixed, re-run `compare_outputs.py` and go through the
flagged differences for both arms, column by column, labeling causes into
the classifier registry as they're identified — falling back to the
original source Excel trackers (`a4dphase2_upload`) as the arbiter wherever
a divergence isn't already an understood, expected pattern. Carries forward
ticket 15's validation requirement: the script's per-column and per-cause
counts should reproduce (or explain deltas from) the parity-presentation
PDF's numbers for `Product_entry_date` (559: typo-rescue 408, CE-typo 71,
sentinel-null 66, off-by-one-day 7), `Product_balance` (480),
`Product_category` (214), `Product_sheet_name` (201),
`Product_received_from` (154), `Product_units_received` (9) — including
resolving the 189-vs-155-tracker discrepancy noted above. Patient-arm
triage (already-sound alignment) is in scope here too, since it was run but
not triaged in ticket 15.

This ticket is still large and investigative — if it doesn't converge in
one session, split the remaining per-column investigation further rather
than leaving it open-ended.
