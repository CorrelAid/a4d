---
id: 22
title: Triage the remaining product raw-stage column mismatches
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
closed: `product_entry_date`'s raw-stage report was found to be ~99%
representation-artifact noise (R stores unparsed Excel serials, Python
stores parsed dates), split into [ticket
20](20-fix-raw-entry-date-representation.md). The other raw-stage product
columns from that session's run are untouched: `product_balance` (2,397),
`product_received_from` (94), `product_released_to` (70), `product_remarks`
(65), `product_units_received` (269), `product_units_returned` (1), and
`product` (685).

Not blocked on ticket 20: these are different columns, and there's no
evidence yet they share entry_date's serial-vs-parsed problem (most are
numeric or plain string columns, not dates) — check each independently
before assuming the same representation issue applies.

**Updated same day, per ticket 18's addendum:** R and Python were both
re-run against the current 248-tracker production set (up from 177) and
`output_r/` now holds that fresh R output (old baseline preserved at
`output_r_155_frozen_backup_2025-11-14`). Refreshed raw-stage counts (same
run, `output/comparison/2026-08-11T232419Z/`): `product_balance` 712 (was
2,397), `product_received_from` 133 (was 94), `product_released_to` 70
(unchanged), `product_remarks` 83 (was 65), `product_units_received` 109
(was 269), `product_units_returned` 1 (unchanged), `product` 721 (was 685).
Use the current `output_r`/`output_python`, not the backup.

## Question

For each remaining raw-stage product column, pull the flagged mismatch rows
and determine whether the divergence is a real R/Python content difference
(worth a named classifier and, if it points at a Python bug, a fix) or
another comparison-tool artifact like ticket 20's (worth a normalization
fix instead). Fall back to the real source Excel trackers as the arbiter
per the map's standing preference. If any raw-stage finding turns out to
also explain part of the corresponding cleaned-stage divergence from
[ticket 21](21-triage-remaining-product-columns.md), note the connection
there rather than re-deriving it.
