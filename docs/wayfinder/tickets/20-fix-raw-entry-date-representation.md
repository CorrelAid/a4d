---
id: 20
title: Normalize the raw-stage product_entry_date comparison so it stops flagging near-universal false mismatches
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
closed: sampling raw-stage `product_entry_date` mismatches directly (e.g.
`2017_Mahosot Hospital A4D Tracker_product_raw.parquet`, sheet `May17`)
found R's raw parquet stores unparsed Excel serial numbers as strings
(`"42872.0"`) while Python's raw parquet already stores parsed ISO
datetimes (`"2017-05-17 00:00:00"`) for the same underlying date. That
representation difference alone accounts for 47,333 of the ~47,644 total
product rows in the raw-stage report — i.e. the raw-stage
`product_entry_date` comparison is currently near-100% noise, not signal.

**Updated same day, per ticket 18's addendum:** R and Python were both
re-run against the current 248-tracker production set (up from 177) and
`output_r/` now holds that fresh R output (the old 155-file baseline is
preserved at `output_r_155_frozen_backup_2025-11-14`). The pattern holds at
the new scale — raw-stage `product_entry_date` is now 65,710 of 65,743
unclassified (99.9%), consistent with the same representation-artifact
theory. Use the current `output_r`/`output_python` (not the backup) when
working this ticket.

## Question

Fix `compare_directory`'s raw-stage cell comparison (`src/a4d/migration/compare.py`)
so `product_entry_date` values are parsed to a common representation (date)
on both sides before diffing, rather than compared as raw strings/serials.
Decide whether this normalization belongs inside `compare_cells` generically
(a column-type hint) or as a raw-stage-specific pre-processing step in
`scripts/compare_outputs.py`, given the cleaned-stage comparison doesn't
have this problem (both sides are already parsed dates there). Re-run `just
compare-outputs` against the USB drive's `output_r`/`output_python` and
confirm the raw-stage `product_entry_date` count drops to a plausible
signal-only number, then triage what (if anything) remains.
